import copy
from functools import total_ordering
import json
import os.path as osp
import yaml
from pprint import pprint as pp
import sys

from fastcache import clru_cache as cache
import click as clk
import numpy as np

from qqq import qio

API_KEY = 'Q0UqPx0czZCCtv1esuv53Trb2m3xHevsljM9l0QI'
URL_REPORT = 'http://api.nal.usda.gov/ndb/reports/'
URL_SEARCH = 'http://api.nal.usda.gov/ndb/search/'

BASE_PARAMS = {'api_key': API_KEY, 'format': 'json'}

CONV_TAB_MASS = {'µg': 1000000,
                 'ug': 1000000,
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
            'Fluoride, F': 'F',
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
            '18:2': 'LA',
            '18:3': 'ALA',
            '20:4': 'AA',
            '20:5': 'EPA',
            '22:5': 'DPA',
            '22:6': 'DHA',
            'Fatty acids, total polyunsaturated': 'pufa',
            'Fatty acids, total monounsaturated': 'mufa',
            'Fatty acids, total saturated': 'sfa',
            'Fatty acids, total trans': 'trans'
            }
IGNORE = set([('Energy', 'kJ'),
              ('Vitamin D (D2 + D3)', 'µg'),
              ('Vitamin D2 (ergocalciferol)', 'µg'),
              ('Vitamin D3 (cholecalciferol)', 'µg')])

AGGR_TAB = {'omega-3': ['ala', 'epa', 'dha', 'dpa'],
            'epa+dha+dpa': ['epa', 'dha', 'dpa'],
            'omega-6': ['la', 'aa']}


# default gram amount
DG = 100

# TODO: fix circular import
import food as ifc

CACHE_FN = osp.join(ifc.CONFIG_PATH, 'cache.json')
if not osp.isfile(CACHE_FN):
    with open(CACHE_FN, 'w') as f:
        json.dump({}, f)
RCP_FN = ifc.RCP_FN


@total_ordering
class Amount:
    def __init__(self, val, unit, balance=True):
        self.val = val
        self.unit = unit
        if self.unit == 'ug':
            self.unit = 'µg'

    def __add__(self, q):
        out = copy.deepcopy(self)
        out.val += q.val*uconv(q.unit, out.unit)
        return out

    def __radd__(self, q):
        return self.__add__(q)

    def __iadd__(self, q):
        self.val += q.val*uconv(q.unit, self.unit)
        return self

    def __mul__(self, num):
        out = copy.deepcopy(self)
        out.val *= num
        return out

    def __rmul__(self, num):
        return self.__mul__(num)

    def __imul__(self, num):
        self.val *= num
        return self

    def __truediv__(self, num):
        out = copy.deepcopy(self)
        out.val /= num
        return out

    def __itruediv__(self, num):
        self.val /= num
        return self

    def __eq__(self, amt):
        return np.isclose(self.val, amt.val*uconv(amt.unit, self.unit))

    def __lt__(self, amt):
        return (not self.__eq__(amt) and
                self.val < amt.val*uconv(amt.unit, self.unit))

    def _balance(self):
        if abs(self.val) < 1:
            if self.unit == 'mg':
                self.unit = 'µg'
                self.val *= 1000
            elif self.unit == 'g':
                self.unit = 'mg'
                self.val *= 1000
            elif self.unit == 'kg':
                self.unit = 'g'
                self.val *= 1000
        elif abs(self.val) > 1000:
            if self.unit == 'µg':
                self.unit = 'mg'
                self.val /= 1000
            elif self.unit == 'mg':
                self.unit = 'g'
                self.val /= 1000
            elif self.unit == 'g':
                self.unit = 'kg'
                self.val /= 1000

    def convert(self, unit):
        self.val *= uconv(self.unit, unit)
        self.unit = unit
        return self

    def __str__(self, color='yellow'):
        return ('{: >10s} {}'
                .format(clk.style('{: 8.1f}'.format(self.val), fg=color),
                        self.unit))


class NutrientList:
    def __init__(self, ini=None):
        self.vals = {}
        self.contents = []
        if ini is not None:
            self.add(ini)

    def balance(self):
        for amt in self.vals.values():
            amt._balance()

    def add(self, item):
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
        for aggr, comp in AGGR_TAB.items():
            for nutr, amt in list(self.vals.items()):
                if nutr in comp:
                    if aggr not in self.vals:
                        self.vals[aggr] = copy.deepcopy(amt)
                    else:
                        self.vals[aggr] += amt
        
    def set(self, nutr, val, unit):
        self.vals[nutr] = Amount(val, unit)

    def __add__(self, nl):
        out = copy.deepcopy(self)
        for name, value in nl.vals.items():
            if name not in out.vals:
                out.vals[name] = value
            else:
                out.vals[name] += value
        out.contents += nl.contents
        return out

    def __iadd__(self, nl):
        for name, value in nl.vals.items():
            if name not in self.vals:
                self.vals[name] = value
            else:
                self.vals[name] += value
        self.contents += nl.contents
        return self
    
    def __sub__(self, nl):
        return self.__add__(-1*nl)

    def __rsub__(self, nl):
        return nl.__add__(-1*self)

    def __isub__(self, nl):
        return self.__iadd__(-1*nl)

    def __mul__(self, num):
        out = copy.deepcopy(self)
        for k in out.vals.keys():
            out.vals[k] *= num
        out.contents = [(a, num*b) for a, b in out.contents]
        return out

    def __rmul__(self, num):
        return self.__mul__(num)

    def __imul__(self, num):
        for k in self.vals.keys():
            self.vals[k] *= num
        self.contents = [(a, num*b) for a, b in self.contents]
        return self

    def print(self, p=True, print_zero=False, filts=None, cd=False):
        out = '\n'.join(['{: >40s}: {}'
                         .format(n, str(self.vals[n]))
                         for n in sorted(self.vals, key=sort_nutrs)
                         if (not np.isclose(self.vals[n].val, 0) or print_zero)
                         ]
                        )
        if p:
            clk.echo(out)
        return out

    def print_delta(self, nl, p=True, print_zero=False, filts=None):
        out = '\n'.join(['{: >40s}: {}'
                         .format(n, str(self.vals[n]))
                         for n in sorted(self.vals, key=sort_nutrs)
                         if (not np.isclose(self.vals[n].val, 0) or print_zero)
                         ]
                        )
        if p:
            clk.echo(out)
        return out

    
    def get_line(self, nutrs, fg='yellow', bg=None, target=None):
        out = ['{: >6s} {: >4s}'for _ in nutrs]
        fmt = []
        fd = isinstance(fg, dict)
        bd = isinstance(fg, dict)
        if target is None:
            target = {}
        out_vals = {n: (self.vals[n] if n not in target else
                    self.vals[n] + -1*target[n]) for n in self.vals}

        for nx, n in enumerate(nutrs):
            try:
                fmt.append(clk.style('{: 8.1f}'.format(out_vals[n].val),
                                     fg=('white'
                                         if not fg or (fd and n not in fg)
                                         else (fg if not fd else fg[n])),
                                     bg=('black'
                                         if not bg or (bd and n not in bg)
                                         else (bg if not bd else bg[n]))))
                fmt.append(out_vals[n].unit)
            except KeyError:
                out[nx] = ' '*13
                continue
        return ' | '.join(out).format(*fmt)


@cache(maxsize=1)
def get_recipes():
    with open(RCP_FN, 'r') as f:
        return yaml.load(f)

@cache(maxsize=1)
def get_cache():
    with open(CACHE_FN, 'r') as f:
        return json.load(f)


def is_food(food):
    rcf = get_recipes()
    return (food in rcf['usda foods'] or food in rcf['custom foods'])


def is_recipe(food):
    rcf = get_recipes()
    return (food in rcf['recipes'] or food in rcf['alias'])


def is_element(s):
    return ((len(s) == 1 and s.isupper()) or
            (len(s) == 2 and s[0].isupper() and s[1].islower()))


def is_omega3(s):
    return s in ['ala', 'epa', 'dha', 'dpa']


def is_omega6(s):
    return s in ['aa', 'la']


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
    if nutr == 'fibre':
        return -56.9
    if nutr == 'epa+dha+dpa' or nutr == 'ala':
        return -56.5
    if nutr == 'omega-6':
        return -56.49
    if nutr in ['pufa', 'mufa', 'sfa', 'trans']:
        return -56.45
    if nutr == 'choline':
        return -56 - 1/3
    # if is_omega3(nutr):
    #     return -56.4
    # if is_omega6(nutr):
    #     return -56.3
    if nutr.upper() == nutr and len(nutr) == 3:
        return -56
    if nutr.lower() == nutr:
        return 50
    if len(nutr) <= 2 and nutr[0].upper() == nutr[0]:
        return -4
    if nutr.startswith('v '):
        return -3
    if ':' not in nutr:
        return -2
    else:
        return -1


def get_nutr_unit(val):
    if ' ' in str(val):
        num, unit = val.split(' ')
        num = float(num)
    else:
        unit = 'g'
        num = float(val)
    return num, unit


@cache(maxsize=(1 >> 10))
def get_usda_nutrients(ndbno):
    c = get_cache()
    try:
        out = c[str(ndbno)]
    except KeyError:
        out = qio.rq_json(URL_REPORT,
                          dict({'ndbno': ndbno,
                                'type': 'f'},
                               **BASE_PARAMS))
        c[ndbno] = out
        with open(CACHE_FN, 'w') as f:
            json.dump(c, f)
    
    try:
        name = out['report']['food']['name']
        out = out['report']['food']['nutrients']
    except KeyError:
        raise ValueError('ndbno "{}" not found in USDA database.'
                         ' check for typos!'.format(ndbno))
    n_out = []
    for n in out:
        n['value'] = float(n['value'])
        if (np.isclose(n['value'], 0) or
                n['name'] is None or
                (n['name'], n['unit']) in IGNORE):
            continue
        for k, v in NAME_TAB.items():
            if k in n['name']:
                n['name'] = v
                break
        if n['name'] is None:
            continue

        if not is_element(n['name']) and not n['name'].startswith('v '):
            n['name'] = n['name'].lower()

        n_out.append(n)

    ret = [(n['name'], n['value'], n['unit']) for n in n_out]

    return name, ret


def correct_usda(food, nl):
    rcp = get_recipes()
    if food in rcp['usda corrections']:
        for k, v in rcp['usda corrections'][food].items():
            num, unit = get_nutr_unit(v)
            nl.set(k, num, unit)
    return nl


@cache(maxsize=(1 >> 10))
def get_food_nl(food):
    # print('call get_food_nl on {}'.format(food))
    rcf = get_recipes()
    if food in rcf['custom foods']:
        out = []
        for ing in rcf['custom foods'][food]:
            nutr, val = list(ing.items())[0]
            if ' ' in str(val):
                num, unit = val.split(' ')
                num = float(num)
            else:
                unit = 'g'
                num = float(val)
            out.append((nutr, num, unit))
        out = NutrientList((food, out))
        return out
    elif food in rcf['usda foods']:
        nl = NutrientList(get_usda_nutrients(
            '{:05d}'.format(rcf['usda foods'][food])))
        # TODO: incorrect, correct_u
        return correct_usda(food, nl)
    else:
        return None


@cache(maxsize=(1 >> 10))
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
    ret.balance()
    return ret


def _test_get_nutrients():
    nl = get_nutrients('test recipe')
    print(nl.contents)
    nl.print()

if __name__ == "__main__":
    print(is_recipe('tilapia and potato'))
