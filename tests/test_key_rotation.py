from cryptography.fernet import Fernet
from services.key_rotation import encrypt, decrypt, rotate

def test_rotate_and_decrypt_with_new_key():
    k1 = Fernet.generate_key().decode()
    k2 = Fernet.generate_key().decode()
    c1 = encrypt("student-01712345678", k1)
    c2 = encrypt("fee-receipt-৳500", k1)
    rotated = rotate([c1, c2], k1, k2)
    # decrypt with new key alone
    assert decrypt(rotated[0], k2) == "student-01712345678"
    assert decrypt(rotated[1], k2) == "fee-receipt-৳500"
    # rollback path: still decrypt with old if new not applied
    assert decrypt(c1, k1) == "student-01712345678"

def test_multi_key_decrypt_after_rotation_chain():
    k1 = Fernet.generate_key().decode()
    k2 = Fernet.generate_key().decode()
    c = encrypt("secret", k1)
    chain = f"{k2},{k1}"
    # MultiFernet tries k2 first then k1
    assert decrypt(c, chain) == "secret"
