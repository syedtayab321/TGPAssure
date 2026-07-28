from modules.gravity.gravity_profiles import get_profile


def test_field_is_more_tolerant_and_strict_more_stringent():
    field=get_profile("field"); standard=get_profile("standard"); strict=get_profile("strict")
    assert field["repeat_rms_warn_mgal"] > standard["repeat_rms_warn_mgal"] > strict["repeat_rms_warn_mgal"]
