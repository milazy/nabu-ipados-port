import hashlib, os
# Batch 4 menu from the installed batch-3 menu (PC side). Every older choice stays selectable.
#   default  Wi-Fi + icons          nabu-launchd-cache=1, iconservicesagent on (CoreImage override)
#            Wi-Fi + icons + AppSync  same + appsync=1 (IPA install)
#            Wi-Fi, no icons        nabu-launchd-cache=2, iconservicesagent off (batch-3 behaviour + wland)
#            FAST without Wi-Fi     (batch 3), SAFE (batch 2)
L = os.path.expanduser(r'~\Desktop\NABU_IPADOS_LAB')
raw = open(L + r'\host-setup\batch3\unixnu.toml', 'rb').read()
assert hashlib.sha256(raw).hexdigest() == 'd64bde3481732d317f17afafedde2ef1cc857dc5e4631498bb4fd76f92598cde', 'menu input changed'
text = raw.decode()
start = text.index('[[entry]]\nid = "xnu-existing-ui-policy"')
nowifi_at = text.index('[[entry]]\nid = "xnu-batch3-nowifi"')
wifi3 = text[start:nowifi_at].rstrip('\n') + '\n'
rest = text[nowifi_at:]
assert 'nabu-disable-watchdogd=2' in wifi3 and 'nabu-launchd-cache' not in text and 'appsync' not in text
a = wifi3.index('args = "'); e = wifi3.index('"\n', a + 8)
T3 = 'title = "iPadOS 17.7 FAST + Wi-Fi (batch 3)"'
def entry(ident, title, extra, watchdog):
    s = (wifi3[:e] + extra + wifi3[e:]).replace('nabu-disable-watchdogd=2', 'nabu-disable-watchdogd=%d' % watchdog, 1)
    s = s.replace(T3, 'title = "%s"' % title, 1)
    if ident:
        s = s.replace('id = "xnu-existing-ui-policy"', 'id = "%s"' % ident, 1)
    return s
icons = entry(None, 'iPadOS 17.7 Wi-Fi + icons (batch 4)', ' nabu-launchd-cache=1', 1)
appsync = entry('xnu-batch4-appsync', 'iPadOS 17.7 Wi-Fi + icons + AppSync IPA (batch 4)', ' nabu-launchd-cache=1 appsync=1', 1)
noicons = entry('xnu-batch4-wifi-noicons', 'iPadOS 17.7 Wi-Fi, no icons (batch 4)', ' nabu-launchd-cache=2', 2)
assert 'appsync=1' in appsync and 'watchdogd=1' in icons and 'watchdogd=2' in noicons
new = text[:start] + icons + '\n' + appsync + '\n' + noicons + '\n' + rest
out = L + r'\host-setup\batch4'
os.makedirs(out, exist_ok=True)
open(out + r'\unixnu.toml', 'wb').write(new.encode())
print('menu', hashlib.sha256(new.encode()).hexdigest())
for line in new.splitlines():
    if line.startswith(('id = "xnu-b', 'id = "xnu-existing', 'default')):
        print(line)
