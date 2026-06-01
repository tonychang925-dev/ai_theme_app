from theme_service.tools.apply_product_runtime_phase3b_theme_profile_v2_patches import PROFILES


def test_phase3b_theme_profile_v2_patches_cover_three_runtime_subjects():
    subject_keys = [profile["subject_key"] for profile in PROFILES]
    assert subject_keys == ["9054404", "9012396", "9043698"]
    assert all(profile["status"] == "accepted_candidate" for profile in PROFILES)
    assert all("accepted_candidate" in profile["quality_flags"] for profile in PROFILES)
