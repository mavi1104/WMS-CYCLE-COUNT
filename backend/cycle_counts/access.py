import hashlib
import hmac

from django.conf import settings
from django.core import signing
from django.contrib.auth.hashers import check_password, make_password


COUNTER_SESSION_SALT = "wms-mobile-counter-session-v1"
COUNTER_SESSION_MAX_AGE = 12 * 60 * 60


# Create an HMAC lookup digest of the ASCII PIN. Troubleshoot: SECRET_KEY consistency and code encoding.
def counter_code_digest(code):
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        code.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


# Hash the counter code using Django's password hasher. Troubleshoot: stored code_hash and configured hashers.
def hash_counter_code(code):
    return make_password(code)


# Compare the PIN against its stored hash. Troubleshoot: code_hash and the supplied code.
def verify_counter_code(code, encoded):
    return check_password(code, encoded)


# Compare the SECRET_KEY-protected PIN digest in constant time for fast normal logins.
# The slower password hash remains available as a fallback after SECRET_KEY rotation.
def verify_counter_digest(code, encoded_digest):
    return bool(encoded_digest) and hmac.compare_digest(
        counter_code_digest(code),
        encoded_digest,
    )


# Sign a token containing the counter and cycle count IDs. Troubleshoot: IDs, signing salt, and SECRET_KEY.
def create_counter_session(counter_id, cycle_count_id):
    return signing.dumps(
        {"counter_id": counter_id, "cycle_count_id": cycle_count_id},
        salt=COUNTER_SESSION_SALT,
        compress=True,
    )


# Validate the counter token signature and age. Troubleshoot: signing salt and the 12-hour expiry.
def read_counter_session(token):
    return signing.loads(
        token,
        salt=COUNTER_SESSION_SALT,
        max_age=COUNTER_SESSION_MAX_AGE,
    )
