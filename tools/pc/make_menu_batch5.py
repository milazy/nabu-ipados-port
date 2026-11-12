import hashlib, os
# Batch 5 menu from the installed batch-4 menu: the three batch-4 entries also get nabu-backlight=1. Older entries stay.
L = os.path.expanduser(r'~\Desktop\NABU_IPADOS_LAB')
raw = open(L + r'\host-setup\batch4\unixnu.toml', 'rb').read()
assert hashlib.sha256(raw).hexdigest() == '403dd353988990c17954ae8d8bbe5e98b94856644349ac414346df7d35c11ceb', 'menu input changed'
lines = raw.decode().split('\n')
out, changed = [], 0
for i, line in enumerate(lines):
    if line.startswith('args = "') and 'nabu-launchd-cache=' in line and 'nabu-backlight' not in line:
        line = line[:-1] + ' nabu-backlight=1"'
        changed += 1
    if line.startswith('title = "') and '(batch 4)' in line:
        line = line.replace('(batch 4)', '(batch 5)')
    out.append(line)
assert changed == 3, changed
new = '\n'.join(out)
o = L + r'\host-setup\batch5'
os.makedirs(o, exist_ok=True)
open(o + r'\unixnu.toml', 'wb').write(new.encode())
print('menu', hashlib.sha256(new.encode()).hexdigest())
