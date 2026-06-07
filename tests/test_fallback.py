import sorters
import ui


def test_print_catalog_groups_and_recommends(monkeypatch, capsys):
    catalog = [
        {"name": "tridesclous2", "group": "ready", "runnable": True,
         "recommended": True, "description": "fast", "present": True, "units": 12},
        {"name": "mountainsort5", "group": "docker", "runnable": False,
         "recommended": False, "description": "container", "present": False, "units": 0},
        {"name": "kilosort4", "group": "gpu", "runnable": False,
         "recommended": False, "description": "gpu", "present": False, "units": 0},
    ]
    ui.print_catalog(catalog)
    out = capsys.readouterr().out
    assert "READY TO USE" in out and "DOCKER SORTERS" in out and "NEEDS A GPU" in out
    assert "tridesclous2" in out and "★" in out


def test_docker_confirm_text_per_state():
    assert "download" in ui.docker_confirm_text("not_installed").lower()
    assert "start" in ui.docker_confirm_text("installed_not_running").lower()
    assert "running" in ui.docker_confirm_text("running").lower()
