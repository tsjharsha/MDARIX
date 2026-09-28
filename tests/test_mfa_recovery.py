from security.mfa_recovery import consume_recovery_code, hash_recovery_codes, issue_recovery_codes


def test_recovery_codes_are_single_use():
    codes = issue_recovery_codes(2)
    hashes = hash_recovery_codes(codes)
    used, remaining = consume_recovery_code(codes[0], hashes)
    assert used is True and len(remaining) == 1
    used_again, still_remaining = consume_recovery_code(codes[0], remaining)
    assert used_again is False and still_remaining == remaining
