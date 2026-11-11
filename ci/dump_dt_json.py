"""Print the root scalars and the product/buttons/chosen nodes of an `ipsw dtree --json` dump."""
import json, sys
t = json.load(open(sys.argv[1]))
def find(n, name, path=''):
    if isinstance(n, dict):
        for k, v in n.items():
            if k == name:
                print(path + '/' + k, json.dumps(v)[:4000])
            find(v, name, path + '/' + k)
    elif isinstance(n, list):
        for i in n:
            find(i, name, path)
root = t.get('device-tree', t)
print('ROOT', {k: v for k, v in root.items() if not isinstance(v, (dict, list))})
for n in ('product', 'buttons', 'chosen'):
    find(t, n)
