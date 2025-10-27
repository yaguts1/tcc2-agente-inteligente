#!/usr/bin/env python3
import json
import urllib.request
import urllib.error
import http.cookiejar

URL = 'http://127.0.0.1:8000'

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

body = {'username': 'ui_test_auto', 'password': 'Secret123', 'display_name': 'UI Auto Test'}
data = json.dumps(body).encode('utf-8')
req = urllib.request.Request(URL + '/api/auth/register', data=data, headers={'Content-Type': 'application/json'})

print('== POST /api/auth/register ==')
try:
    r = opener.open(req)
    print('STATUS:', r.getcode())
    print('RESPONSE:', r.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print('HTTP ERROR:', e.code)
    try:
        print(e.read().decode('utf-8'))
    except Exception:
        pass
except Exception as e:
    print('ERROR:', e)

print('\n== GET /api/auth/me with session cookies ==')
try:
    r2 = opener.open(URL + '/api/auth/me')
    print('STATUS:', r2.getcode())
    print('RESPONSE:', r2.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print('HTTP ERROR:', e.code)
    try:
        print(e.read().decode('utf-8'))
    except Exception:
        pass
except Exception as e:
    print('ERROR:', e)
