from app.decoder import scale_amount

def test_uint256_amount_is_preserved_as_raw_string():
    raw = str(2**255 + 123)
    assert isinstance(raw, str)
    assert scale_amount(raw, 18) > 0