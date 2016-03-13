import json
import os.path as osp
import yaml
from pprint import pprint as pp
import sys

import click as clk
import numpy as np

from qqq import qio

API_KEY = 'Q0UqPx0czZCCtv1esuv53Trb2m3xHevsljM9l0QI'
URL_REPORT = 'http://api.nal.usda.gov/ndb/reports/'
URL_SEARCH = 'http://api.nal.usda.gov/ndb/search/'

BASE_PARAMS = {'api_key': API_KEY, 'format': 'json'}

CONV_TAB_MASS = {'µg': 1000000,
                 'mg': 1000,
                 'g': 1,
                 'kg': 0.001}
CONV_TAB_ENERGY = {'kcal': 1,
                   'kJ':   4.184}
NAME_TAB = {'Water': 'water',
            'Ash': None,
            'Energy': 'energy',
            'Protein': 'protein',
            'Total lipid (fat)': 'fat',
            'Cholesterol': 'cholesterol',
            'Sugars, total': 'sugar',
            'Fiber, total dietary': 'fibre',
            'Carbohydrate': 'carbs',
            'Calcium, Ca': 'Ca',
            'Iron, Fe': 'Fe',
            'Magnesium, Mg': 'Mg',
            'Phosphorus, P': 'P',
            'Potassium, K': 'K',
            'Sodium, Na': 'Na',
            'Zinc, Zn': 'Zn',
            'Copper, Cu': 'Cu',
            'Manganese, Mn': 'Mn',
            'Selenium, Se': 'Se',
            'Vitamin A, RAE': None,
            'Vitamin A, IU': 'v A',
            'Vitamin C, total ascorbic acid': 'v C',
            'Vitamin E (alpha-tocopherol)': 'v E',
            'Vitamin D': 'v D',
            'Choline, total': 'choline',
            'Thiamin': 'v B1',
            'Riboflavin': 'v B2',
            'Niacin': 'v B3',
            'Pantothenic acid': 'v B5',
            'Vitamin B-6': 'v B6',
            'Biotin': 'v B7',
            'Folate, total': 'v B9',
            'Folate, food': None,
            'Folate, DFE': None,
            'Folic': None,
            'Vitamin B-12': 'v B12',
            'Vitamin K (phylloquinone)': 'v K',
            '18:2': 'omega-6',
            '18:3': 'ALA',
            '20:4': 'omega-6',
            '20:5': 'EPA',
            '22:5': 'DPA',
            '22:6': 'DHA'
            }
IGNORE = set([('Energy', 'kJ'),
              ('Vitamin D (D2 + D3)', 'µg'),
              ('Vitamin D2 (ergocalciferol)', 'µg'),
              ('Vitamin D3 (cholecalciferol)', 'µg')])

AGGR_TAB = {'omega-3': ['ALA', 'EPA', 'DHA', 'DPA']}
AGGR_TAB = {'sugar': ['Sucrose', 'Lactose']}

# default gram amount
DG = 100

import interface as ifc

NDB_CACHE_ADV_FN = osp.join(ifc.CONFIG_PATH, 'cache_advanced.json')
NDB_CACHE_BSC_FN = osp.join(ifc.CONFIG_PATH, 'cache_basic.json')
RCP_FN = osp.join(ifc.CONFIG_PATH, 'recipes.yaml')

class Amount:
    def __init__(self, val, unit, balance=True):
        self.val = val
        self.unit = unit
        self.balance = balance

    def __add__(self, q):
        self.val += q.val*uconv(q.unit, self.unit)
        if self.balance:
            self._balance()
        return self

    def __mul__(self, num):
        self.val *= num
        if self.balance:
            self._balance()
        return self

    def _balance(self):
        if abs(self.val) < 1:
            if self.unit == 'mg':
                self.unit = 'µg'
                self.val *= 1000
            if self.unit == 'g':
                self.unit = 'mg'
                self.val *= 1000
            if self.unit == 'kg':
                self.unit = 'g'
                self.val *= 1000
        elif abs(self.val) > 1000:
            if self.unit == 'µg':
                self.unit = 'mg'
                self.val /= 1000
            if self.unit == 'mg':
                self.unit = 'g'
                self.val /= 1000
            if self.unit == 'g':
                self.unit = 'kg'
                self.val /= 1000

    def convert(self, unit):
        self.val *= uconv(self.unit, unit)
        self.unit = unit

    def __str__(self, fmt=None):
        return ('{: >10s} {}'
                .format(clk.style('{: 8.3f}'.format(self.val), fg='yellow'),
                        self.unit))


class NutrientList:
    def __init__(self, ini=None):
        # print('creating nutrient list with ini {}'.format(ini[0] if ini is not
        #     None else None))
        self.vals = {}
        self.contents = []
        if ini is not None:
            self.add(ini)

    def add(self, item):
        # print('adding item {} ({} grams) to nl {}'.format(item[0],
        #        DG, self))
        name, nutrs = item
        self.contents.append((name, DG))
        for nutr in nutrs:
            n = nutr[0]
            v = nutr[1]
            amt = Amount(v, nutr[2])
            if n not in self.vals:
                self.vals[n] = amt
            else:
                self.vals[n] += amt

        # TODO: TODO
        for ak, vals in AGGR_TAB.items():
            for nk in self.vals.keys():
                if nk in vals:
                    pass

    def __add__(self, nl):
        for name, value in nl.vals.items():
            if name not in self.vals:
                self.vals[name] = value
            else:
                self.vals[name] += value
        self.contents += nl.contents
        return self

    def __mul__(self, num):
        for k in self.vals.keys():
            self.vals[k] *= num
        self.contents = [(a, num*b) for a, b in self.contents]
        return self

    def __rmul__(self, num):
        return self.__mul__(num)
    
    def __imul__(self, num):
        return self.__mul__(num)

    def print(self, p=True, print_zero=False, filts=None):
        out = '\n'.join(['{: >40s}: {}'
                         .format(n, str(self.vals[n]))
                         for n in sorted(self.vals, key=sort_nutrs)
                         if (not np.isclose(self.vals[n].val, 0) or print_zero)
                         ]
                        )
        if p:
            clk.echo(out)
        return out
    
    def get_line(self, nutrs, color=True):
        out = ['{: >10s} {: >4s}'for _ in nutrs]
        fmt = []
        for nx, n in enumerate(nutrs):
            try:
                fmt.append(clk.style('{: 9.3f}'.format(self.vals[n].val),
                                     fg=('yellow' if color else 'white')))
                fmt.append(self.vals[n].unit)
            except KeyError:
                out[nx] = ' '*14
                continue
        return ' | '.join(out).format(*fmt)


def get_recipes():
    with open(RCP_FN, 'r') as f:
        return yaml.load(f)


def is_usda_food(food):
    rcf = get_recipes()
    return (food in rcf['usda foods'])

def is_recipe(food):
    rcf = get_recipes()
    return (food in rcf['recipes'] or food in rcf['alias'])


def uconv(u1, u2):
    if u1 == u2:
        return 1
    try:
        return CONV_TAB_MASS[u2]/CONV_TAB_MASS[u1]
    except KeyError:
        return CONV_TAB_ENERGY[u2]/CONV_TAB_ENERGY[u1]


def lookup_food(s):
    j = qio.rq_json(URL_SEARCH, dict({'q': s}, **BASE_PARAMS))
    return j


def sort_nutrs(nutr):
    print(nutr)
    if ':' in nutr:
        return 100
    if nutr == 'energy':
        return -60
    if nutr == 'protein':
        return -59
    if nutr == 'carbs':
        return -58
    if nutr == 'fat':
        return -57
    if 'omega' in nutr:
        return -56.5
    if nutr.upper() == nutr and len(nutr) == 3:
        return -56
    elif nutr.lower() == nutr:
        return -5
    elif len(nutr) <= 2 and nutr[0].upper() == nutr[0]:
        return -4
    elif nutr.startswith('v '):
        return -3
    elif ':' not in nutr:
        return -2
    else:
        return -1

def get_usda_nutrients(ndbno, advanced=True):
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
        if (n['name'], n['unit']) in IGNORE:
            continue
        if np.isclose(n['value'], 0):
            continue
        for k, v in NAME_TAB.items():
            if k in n['name']:
                n['name'] = v
                break
        if n['name'] is not None:
            n_out.append(n)

    ret = [(n['name'], n['value'], n['unit']) for n in n_out]

    return name, ret


def correct_usda(food, nutr):
    # TODO: TODO
    # raise NotImplementedError()
    return nutr


def get_food_nl(food):
    # print('call get_food_nl on {}'.format(food))
    rcf = get_recipes()
    if food in rcf['custom foods']:
        out = []
        for ing in rcf['custom foods'][food]:
            unit = ing.pop('unit', 'g')
            name, value = list(ing.items())[0]
            out.append((name, value, unit))
        out = NutrientList((food, out))
        return out
    elif food in rcf['usda foods']:
        out = get_usda_nutrients('{:05d}'.format(rcf['usda foods'][food]))
        # TODO: incorrect, correct_u
        out = NutrientList(correct_usda(food, out))
        return out
    else:
        return None


def get_nutrients(name, mult=1):
    # print('call get nutrients with name {}, mult {}'.format(name, mult))
    d = get_recipes()
    if name in d['usda foods'] or name in d['custom foods']:
        nl = get_food_nl(name)
    else:
        if name in d['recipes']:
            rcp = d['recipes'][name]
        else:
            try:
                return get_nutrients(d['alias'][name], mult=mult)
            except KeyError:
                clk.echo('food {} not found'.format(clk.style(name, fg='red')))
                sys.exit(1)
        nl = NutrientList()
        for food, amount in rcp.items():
            if food in d['recipes'] or food in d['alias']:
                nl_n = get_nutrients(food, mult=amount)
            else:
                nl_n = get_nutrients(food, mult=amount/DG)
            nl += nl_n

    ret = mult*nl
    return ret


def _test_get_nutrients():
    nl = get_nutrients('test recipe')
    print(nl.contents)
    nl.print()

if __name__ == "__main__":
    _test_get_nutrients()
    # nl = get_nutrients('test recipe')
    # nl.print()
    # pp(lookup_food('avocado'))
    # pp(get_recipe('avocado sandwich'))
