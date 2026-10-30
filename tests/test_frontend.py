"""Exercise the JavaScript emitted into the frontend template."""

import asyncio
from html import escape
import json
import re
import shutil
import subprocess
from unittest.mock import MagicMock, patch

from homeassistant.components import frontend
from homeassistant.core import HomeAssistant
from jinja2 import Template
import pytest

from custom_components.favicon import apply_hooks, async_setup
from custom_components.favicon.const import CONF_TITLE


@pytest.mark.parametrize("title", ["Test Home Assistant", 'Home "A" & </script><script>test'])
async def test_title_updates_are_stable(hass: HomeAssistant, title: str) -> None:
    """Preserve page names and avoid repeated writes of the configured title.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        title (str): Configured title, including characters requiring escaping.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to execute the emitted frontend JavaScript")
    with (
        patch.object(
            frontend.IndexView,
            "get_template",
            return_value=Template("<title>Home Assistant</title><body></body>"),
        ),
        patch.object(hass, "http", MagicMock()),
        patch("custom_components.favicon.find_icons", return_value={}),
        patch.object(frontend, "add_manifest_json_key"),
    ):
        await async_setup(hass, {})
        await apply_hooks(hass, {CONF_TITLE: title})
        rendered = frontend.IndexView.get_template(None).render()
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
