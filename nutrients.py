import json
import os.path as osp
import yaml
from pprint import pprint as pp
from qqq import qio

import interface as ifc

NDB_CACHE_ADV_FN = osp.join(ifc.CONFIG_PATH, 'cache_advanced.json')
NDB_CACHE_BSC_FN = osp.join(ifc.CONFIG_PATH, 'cache_basic.json')
RCP_FN = osp.join(ifc.CONFIG_PATH, 'recipes.yaml')

API_KEY = 'Q0UqPx0czZCCtv1esuv53Trb2m3xHevsljM9l0QI'
URL_REPORT = 'http://api.nal.usda.gov/ndb/reports/'
URL_SEARCH = 'http://api.nal.usda.gov/ndb/search/'

BASE_PARAMS = {'api_key': API_KEY, 'format': 'json'}

CONV_TAB = {'µg': 1000000,
            'mg': 1000,
            'kg': 0.001}
NAME_TAB = {'total lipid (fat)': 'fat',
            'thiamin': 'v B1',
            'riboflavin': 'v B2',
            'niacin': 'v B3',
            'pantothenic acid': 'v B5',
            'biotin': 'v B7',
            'folate': 'v B9',
            'folate, dfe': 'v B9',
            'fiber, total dietary': 'fibre',
            'carbohydrate, by difference': 'carbs',
            'sugars, total': 'sugar'
            }
IGNORE = set(['water'])


def uconv(u1, u2):
    if u1 == u2:
        return 1
    try:
        return CONV_TAB[u2]/CONV_TAB[u1]
    except:
        return 1


def lookup_food(s):
    j = qio.rq_json(URL_SEARCH, dict({'q': s}, **BASE_PARAMS))
    return j


def canonicalize_name(name, group):
    group = group.lower()
    if group == 'minerals':
        return name.split(',')[1].strip()
    elif name.startswith('Vitamin'):
        name = 'v {}'.format(name.split(' ')[1])
        name = name.replace('-', '')
        name = name.rstrip(',')
        return name

    name = name.lower()
    return NAME_TAB.get(name, name.lower())


def fetch_nutrients(ndbno, advanced=False):
    print(ndbno)
    fn = (NDB_CACHE_ADV_FN if advanced else NDB_CACHE_BSC_FN)
    with open(fn, 'r') as f:
        c = json.load(f)
    try:
        out = c[str(ndbno)]
    except KeyError:
        out = qio.rq_json(URL_REPORT,
                          dict({'ndbno': ndbno,
                                'type': 'f' if advanced else 'b'},
                               **BASE_PARAMS))
        c[ndbno] = out
        with open(fn, 'w') as f:
            json.dump(c, f)

    name = out['report']['food']['name']
    out = out['report']['food']['nutrients']
    n_out = []
    for n in out:
        n['value'] = float(n['value'])
        n['name'] = canonicalize_name(n['name'], n['group'])
        if (n['name'] == 'v A' or n['name'] == 'v D') and 'µg' in n['unit']:
            continue
        else:
            n_out.append(n)

    ret = [(n['name'], n['value'], n['unit'])
           for n in n_out if n['name'] not in IGNORE]
    return name, ret


def correct_usda(food, nutr):
    # raise NotImplementedError()
    return nutr


def get_food_nutrients(food):
    print(food)
    with open(RCP_FN, 'r') as f:
        rcf = yaml.load(f)
    if food in rcf['usda foods']:
        out = fetch_nutrients('{:05d}'.format(rcf['usda foods'][food]))
        print(out)
        return correct_usda(food, out)
    elif food in rcf['alias']:
        return get_food_nutrients(rcf['alias'][food])


def get_recipe(rn):
    with open(RCP_FN, 'r') as f:
        rcf = yaml.load(f)
    try:
        return rcf['recipes'][rn]
    except:
        return rcf['recipes'][rcf['alias'][rn]]


def get_recipe_nutrients(rn):
    ings = get_recipe(rn)
    nuts = {}
    for k, v in ings.items():
        print(k, v)
        nutr = get_food_nutrients(k)
        print(nutr)



def _test():
    print('getting recipe')
    pp(get_recipe('avocado sandwich'))
    print('looking up food')
    pp(lookup_food("Oats"))
    print('getting nutrients')
    fetch_nutrients(16033)

if __name__ == "__main__":
    # _test()
    get_recipe_nutrients('mea')
    # pp(lookup_food('avocado'))
    # pp(get_recipe('avocado sandwich'))
