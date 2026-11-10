"""Settings: defaults, validation and parsing."""

import copy

import pytest

from nutcore import library


def test_default_config_is_valid_and_a_fresh_copy():
    config = library.default_config()
    assert library.validate(config) == []
    config["nuts"].clear()
    assert len(library.default_config()["nuts"]) == 1


def test_parse_gives_typed_library():
    lib = library.parse(library.default_config())
    nut = lib.get("m3sq")
    assert nut.across_flats == 5.5 and nut.flat.width == (5.7, 5.9)
    assert lib.settings.on_error == "block"


def _broken(change):
    config = copy.deepcopy(library.default_config())
    change(config)
    return library.validate(config)


def test_validation_rejects_bad_values():
    assert _broken(lambda c: c["nuts"][0]["flat"].update(width=[5.9, 5.7]))
    assert _broken(lambda c: c["nuts"][0].update(thickness=0))
    assert _broken(lambda c: c["nuts"][0].update(key="M3__SQ"))
    assert _broken(lambda c: c["nuts"].append(dict(c["nuts"][0], key="m3sq")))
    assert _broken(lambda c: c["settings"].update(on_error="ignore"))
    assert _broken(lambda c: c["settings"].update(firmware="grbl"))
    assert _broken(lambda c: c.update(schema=2))


def test_unknown_placeholder_is_a_template_error():
    errors = _broken(lambda c: c["settings"]["templates"].update(klipper="INSERT X={xx}"))
    assert len(errors) == 1 and errors[0].startswith("E_TEMPLATE")


def test_parse_raises_with_all_errors():
    config = library.default_config()
    config["nuts"][0]["thickness"] = -1
    with pytest.raises(library.ConfigError) as info:
        library.parse(config)
    assert info.value.errors
