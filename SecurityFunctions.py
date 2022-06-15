import uuid
from Crypto.Random import get_random_bytes
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import scrypt
from hashlib import blake2b
from hmac import compare_digest

SECRET_KEY = b"pseudorandomly generated secret key"
AUTH_SIZE = 32

"""
Some parameters in GCM mode is:
- key (bytes) - the cryptographic key

- mode - the constant Crypto.Cipher.<algorithm>.MODE_GCM

- nonce (bytes) - the value of the fixed nonce. It must be unique for the combination message/key. If not present, the library creates a random nonce (16 bytes long for AES).

- mac_len (integer) - the desired length of the MAC tag, from 4 to 16 bytes (default: 16).
"""


def encrypt_info(string):
    """Encryption will return a tuple of ciphertext, tag, nonce, salt"""
    plaintext = bytes(string, "utf-8")  # Get this from somewhere else like input()

    salt = get_random_bytes(32)  # Generate salt

    # Generate a key using the password and salt
    key = scrypt(plaintext, salt, key_len=32, N=2 ** 17, r=8, p=1)

    cipher = AES.new(key, AES.MODE_GCM)  # Create a cipher object to encrypt data

    nonce = cipher.nonce  # Get the nonce generated by the cipher
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)  # Encrypt and digest the plaintext

    return ciphertext, tag, nonce, salt


def decrypt_info(ciphertext, tag, nonce, salt):
    """Decryption will return the plaintext"""
    # Generate a key using the password and salt again
    key = scrypt(plaintext, salt, key_len=32, N=2 ** 17, r=8, p=1)

    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)  # Create a cipher object to decrypt data
    plaintext = cipher.decrypt(ciphertext)

    try:
        cipher.verify(tag)  # Verify the tag
        print("The message is authentic: {}".format(plaintext))
    except ValueError:
        print("Key is incorrect or message is corrupted.")

    return plaintext

""" UUID v5 for user id"""
def generate_uuid5(username):
    """ 
    Generates a UUID using a SHA-1 hash of a namespace UUID and a name
    """
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, username))

""" UUID v4 for book id"""
def generate_uuid4():
    return str(uuid.uuid4())


""" Keyed Hashing algorithm """
def sign(data):  # data is a byte string
    h = blake2b(digest_size=AUTH_SIZE, key=SECRET_KEY)
    h.update(data)

    return h.hexdigest().encode("utf-8")


def verify(data, sig):
    good_sig = sign(data)

    return compare_digest(good_sig, sig)
