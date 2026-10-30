"""Exercise the JavaScript emitted into the frontend template."""

import asyncio
from html import escape
import json
import re
import shutil
import subprocess
from unittest.mock import patch

from homeassistant.components import frontend
from homeassistant.core import HomeAssistant
from jinja2 import Template
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.favicon import async_setup_entry
from custom_components.favicon.const import CONF_TITLE, DOMAIN


@pytest.mark.parametrize("title", ["Test Home Assistant", 'Home "A" & </script><script>test'])
async def test_title_updates_are_stable(
    favicon_frontend: HomeAssistant, hass_client: ClientSessionGenerator, title: str
) -> None:
    """Preserve page names and avoid repeated writes of the configured title.

    Args:
        favicon_frontend (HomeAssistant): Real frontend with isolated icon files.
        hass_client (ClientSessionGenerator): Authenticated HTTP client factory.
        title (str): Configured title, including characters requiring escaping.
    """
    hass = favicon_frontend
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to execute the emitted frontend JavaScript")
    with patch.object(
        frontend.IndexView,
        "get_template",
        return_value=Template("<title>Home Assistant</title><body></body>"),
    ):
        await async_setup_entry(hass, MockConfigEntry(domain=DOMAIN, data={CONF_TITLE: title}))
        client = await hass_client()
        response = await client.get("/")
        assert response.status == 200
        rendered = await response.text()
    assert f"<title>{escape(title)}</title>" in rendered
    script = re.search(r'<script type="module">(.*?)</script>', rendered, re.DOTALL)
    assert script is not None
    harness = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
let input = '';
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', async () => {
    const {script, title} = JSON.parse(input);
    let tick, current, writes;
    const label = {textContent: ''};
    const sidebar = {prototype: {updated() {}}};
    const document = {
        get title() {return current;},
        set title(value) {current = value; writes++;},
    };
    vm.runInNewContext(script, {
        document,
        customElements: {whenDefined: () => Promise.resolve(), get: () => sidebar},
        window: {setInterval: callback => tick = callback},
    });
    await Promise.resolve();
    sidebar.prototype.updated.call({shadowRoot: {querySelector: () => label}}, {});
    assert.equal(label.textContent, title);
    for (const page of ['Home Assistant', 'Settings – Home Assistant',
                        'Settings - Home Assistant', 'A – B – Home Assistant',
                        'Unrelated page']) {
        current = page;
        writes = 0;
        const expected = page.endsWith('Home Assistant')
            ? page.slice(0, -'Home Assistant'.length) + title : page;
        for (let i = 0; i < 10; i++) tick();
        assert.equal(current, expected);
        assert.equal(writes, expected === page ? 0 : 1);
    }
});
"""
    result = await asyncio.to_thread(
        subprocess.run,
        [node, "-e", harness],
        input=json.dumps({"script": script.group(1), "title": title}),
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
