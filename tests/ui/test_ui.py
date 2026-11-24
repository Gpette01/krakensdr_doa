# UI tests without a browser: page layouts, component IDs, and a loopback server smoke test.
# The UI runs in a subprocess against a sandbox copy (see sandbox.py); its process calls are blocked there.
import ast
import json

import pytest
from ui import sandbox

WEB_INTERFACE = sandbox.REPO_ROOT / "_ui" / "_web_interface"
PUSHING_SOURCES = [
    "utils.py",
    "kraken_web_doa.py",
    "kraken_web_spectrum.py",
    "callbacks/main.py",
    "callbacks/update_daq_params.py",
    "callbacks/display_page.py",
]
VALUE_COMPONENTS = {"Input", "Dropdown", "Checklist", "RadioItems", "Slider", "Textarea"}


@pytest.fixture(scope="module")
def layout(tmp_path_factory):
    line, _ = sandbox.run_probe(tmp_path_factory.mktemp("ui_layout"), "layout")
    return json.loads(line)


def components(layout):
    return [item for page in layout["pages"].values() for item in page]


def all_ids(layout):
    return {item["id"] for item in components(layout) if item["id"] is not None}


def component_types(layout):
    return {item["id"]: item["type"] for item in components(layout) if item["id"] is not None}


def pushed_properties():
    """(component id, property) for every literal app.push_mods({...}) in the UI sources.

    Keys built from a loop variable, such as "vfo_" + str(i) + "_freq", are evaluated with i = 0.
    """
    pushed = set()
    for relative in PUSHING_SOURCES:
        path = WEB_INTERFACE / relative
        for node in ast.walk(ast.parse(path.read_text(), str(path))):
            is_push = isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "push_mods"
            if not is_push or not node.args or not isinstance(node.args[0], ast.Dict):
                continue
            for key, value in zip(node.args[0].keys, node.args[0].values):
                component = eval(compile(ast.Expression(key), str(path), "eval"), {"str": str, "i": 0})
                for prop in value.keys:
                    pushed.add((component, prop.value))
    return pushed


def test_every_page_builds(layout):
    sizes = {name: len(items) for name, items in layout["pages"].items()}
    assert all(sizes.values()), sizes
    assert len(layout["callbacks"]) == 42


def test_every_callback_id_exists(layout):
    ids = all_ids(layout)
    missing = set()
    for callback in layout["callbacks"]:
        for component in callback["inputs"] + callback["state"] + callback["outputs"]:
            # dash_devices gives callbacks with no output a placeholder output named "_none".
            if component != "_none" and component not in ids:
                missing.add(component)
    assert not missing


def test_pushed_ids_are_found_in_the_sources():
    """Guards the AST scan above: if it found nothing, the two ID tests below would pass vacuously."""
    assert len(pushed_properties()) > 50


@pytest.mark.xfail(
    strict=True, raises=AssertionError, reason="D-43: body_avg_powers is pushed but no element has that ID"
)
def test_every_pushed_id_exists(layout):
    ids = all_ids(layout)
    assert sorted({component for component, _ in pushed_properties()} - ids) == []


@pytest.mark.xfail(
    strict=True, raises=AssertionError, reason="D-28: preset values are pushed to label IDs, not to the inputs"
)
def test_every_pushed_value_goes_to_an_input(layout):
    types = component_types(layout)
    wrong = sorted(
        (component, types[component])
        for component, prop in pushed_properties()
        if prop == "value" and component in types and types[component] not in VALUE_COMPONENTS
    )
    assert wrong == []


@pytest.mark.xfail(
    strict=True, raises=AssertionError, reason="D-43: tooltip target label_daq_decimated_bw does not exist"
)
def test_every_tooltip_target_exists(layout):
    ids = all_ids(layout)
    targets = {item["target"] for item in components(layout) if item["type"] == "Tooltip"}
    assert targets, "no tooltips found"
    assert sorted(targets - ids) == []


@pytest.mark.parametrize("page", ["main", "config", "spectrum", "doa"])
def test_ids_are_unique_on_each_page(layout, page, request):
    if page == "config":
        request.applymarker(
            pytest.mark.xfail(strict=True, raises=AssertionError, reason="T-15: label_en_basic_daq_cfg is used twice")
        )
    ids = [item["id"] for item in layout["pages"][page] if item["id"] is not None]
    assert sorted({i for i in ids if ids.count(i) > 1}) == []


def test_server_answers_on_loopback(tmp_path):
    port = sandbox.free_port()
    line, output = sandbox.run_probe(tmp_path, "server", port)
    results = json.loads(line)
    for path in ("/", "/_dash-layout", "/_dash-dependencies", "/config", "/doa", "/spectrum"):
        assert results[path].get("status") == 200, (path, results[path], output[-2000:])
    assert results["/_dash-dependencies"]["callbacks"] == 42
