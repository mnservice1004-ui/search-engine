"""Vercel build step: generate a read-only catalog without the operating DB."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from deployment_catalog import build_catalog


def verify_sms_authentication():
    """Verify build credentials with a read-only request; never send a message."""
    http_status = 0
    provider_code = 'unclassified'
    verified = False
    allowed_codes = {
        'InvalidAPIKey', 'InvalidApiKey', 'SignatureDoesNotMatch',
        'RequestTimeTooSkewed', 'DuplicatedSignature', 'Unauthorized',
        'Forbidden', 'IpNotAllowed', 'InvalidIp', 'TooManyRequests',
    }
    try:
        import math
        import httpx
        from solapi.lib.authenticator import Authenticator
        from sms_service import _solapi_settings

        api_key, api_secret, _sender = _solapi_settings()
        if not api_key or not api_secret:
            raise ValueError('Missing SMS authentication settings')
        authorization = Authenticator(api_key, api_secret).get_auth_info()
        transport = httpx.HTTPTransport(retries=0)
        with httpx.Client(transport=transport, timeout=15,
                          follow_redirects=False, trust_env=False) as client:
            response = client.get('https://api.solapi.com/cash/v1/balance',
                                  headers={'Authorization': authorization})
        status = response.status_code
        http_status = status if type(status) is int and 100 <= status <= 599 else 0
        payload = response.json()
        if http_status == 200:
            verified = isinstance(payload, dict) and all(
                type(payload.get(field)) in (int, float)
                and math.isfinite(payload[field])
                for field in ('balance', 'point')
            )
        elif isinstance(payload, dict):
            code = payload.get('errorCode')
            if type(code) is str and code in allowed_codes:
                provider_code = code
    except Exception:
        # Do not expose exceptions, request headers, response bodies or balances.
        pass
    if not verified:
        print(f'SMS auth preflight: http_status={http_status} provider_code={provider_code}')
        raise SystemExit('Release blocked: SMS authentication preflight failed.') from None
    print('SMS auth preflight: auth_verified http_status=200')


def main():
    if os.getenv('VERCEL') == '1':
        from sms_service import sms_capability
        if not sms_capability()['ready']:
            raise SystemExit('Release blocked: first public release requires configured live SMS and shared safety limits. No mock fallback.')
        if os.getenv('SMS_AUTH_PREFLIGHT') == '1':
            verify_sms_authentication()
    print(build_catalog(ROOT / 'data/deployment_catalog.json', ROOT / 'data/deployment_catalog.db'))


if __name__ == '__main__':
    main()
