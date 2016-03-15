#! /usr/bin/python
import click as clk
import datetime as dtm
import numpy as np
import os
import os.path as osp
import re
from subprocess import call

from fastcache import clru_cache as cache
import yaml

EDITOR = os.environ.get('EDITOR', 'vim')

RE_ANSI = re.compile(r'(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]')
RE_LOG = re.compile(r'^([0-9]{2}) ([0-9]{2}:[0-9]{2}) - (.*?)(?:$| x(.*?)$)')

CONFIG_PATH = osp.join(osp.expanduser('~'), '.config/nutrition/')
CFG_FN = osp.join(CONFIG_PATH, 'config.yaml')
RCP_FN = osp.join(CONFIG_PATH, 'recipes.yaml')
GOAL_FN = osp.join(CONFIG_PATH, 'goal.yaml')


import nutrients as ntr


@cache(maxsize=1)
def read_config():
    with open(CFG_FN, 'r') as f:
        d = yaml.load(f)
    return d


def read_goal():
    cfg = read_config()
    goal = cfg['goal']
    with open(GOAL_FN, 'r') as f:
        g = yaml.load(f)
    try:
        return g[goal]
    except KeyError:
        clk.echo('goal {} not found'.format(clk.style(goal, fg='red')))



def get_logfn(month=None):
    LOG_FN = osp.join(CONFIG_PATH, '{}-log.txt')
    if month is None:
        month = dtm.datetime.now().isoformat()[:7]
    return LOG_FN.format(month)


def get_loglines(month=None):
    with open(get_logfn(month), 'r') as f:
        lines = list(f.readlines())
    return [RE_LOG.findall(line)[0] for line in lines if line]


def mk_header(s, pad=100):
    l = len(s)
    ls = len(RE_ANSI.sub('', s))
    s = '{0:=^{1}}'.format(' ' + s + ' ', pad+l-ls) + '\n'
    return s


def pp_nutrients(nuts, amount=ntr.DG):
    itms = ['{: >40s}: {: >10s} {}'.format(n,
                                           clk.style('{: 8.3f}'
                                                     .format(v*amount/ntr.DG),
                                                     fg='yellow'),
                                           u)
            for n, v, u in nuts if not np.isclose(v, 0)]

    return '\n'.join(itms)


@clk.command()
@clk.argument('name')
def find(name):
    j = ntr.lookup_food(name)
    if 'errors' in j:
        clk.echo(mk_header(clk.style('no results found', fg='red')))
        return
    res = j['list']
    out = 'searching for {}: {} found'.format(clk.style(name, fg='cyan'),
                                              clk.style(str(res['total']),
                                                        fg='red'))
    itms = ['[{:5s}] {}'.format(clk.style(str(n['ndbno']), fg='yellow'),
                                n['name'])
            for n in res['item']]
    out = mk_header(out)
    out += '\n'.join(itms)
    clk.echo_via_pager(out)


@clk.command()
@clk.argument('query', nargs=1)
@clk.argument('amount', nargs=1, required=False)
def info(query, **kwargs):
    rcp = ntr.is_recipe(query) or ntr.is_food(query)

    amount = kwargs['amount']
    if amount is None:
        amount = ntr.DG if not rcp else 1
    else:
        amount = float(amount)

    if rcp:
        nl = ntr.get_nutrients(query)
        out = 'looking up {}'.format(clk.style(query, fg='magenta'))
    else:
        name, info = ntr.get_usda_nutrients(query)
        nl = ntr.NutrientList((name, info))
        out = 'looking up [{:5s}] {}'.format(clk.style(str(query),
                                                       fg='yellow'),
                                             clk.style(name, fg='cyan'))
    nl *= (amount/(ntr.DG if not rcp else 1))
    nl.balance()

    out = mk_header(out)
    if not rcp:
        out += mk_header('values for {}'
                         .format(clk.style(str(int(amount)) + ' g',
                                           fg='red')))
        out += nl.print(p=False)
    else:
        out += nl.print(p=False)

    clk.echo_via_pager(out)


@clk.command()
@clk.argument('dbno1', nargs=1, required=True)
@clk.argument('dbno2', nargs=1, required=True)
@clk.argument('amount', nargs=1, required=False)
@clk.option('-t', nargs=1, default=1.1)
@clk.option('-n', is_flag=True, nargs=1, default=False)
@clk.option('-nz', is_flag=True, nargs=1, default=False)
def compare(dbno1, dbno2, **kwargs):
    thr = max(float(kwargs['t']), 1.)
    norm = kwargs['n']
    nz = kwargs['nz']
    amt = ntr.DG if kwargs['amount'] is None else float(kwargs['amount'])
    if ntr.is_food(dbno1) or ntr.is_recipe(dbno1):
        nl1 = ntr.get_nutrients(dbno1)
        h1 = clk.style(dbno1, fg='magenta')
    else:
        nl1 = ntr.NutrientList(ntr.get_usda_nutrients(dbno1))
        h1 = '{} [{:5s}]'.format(clk.style(nl1.self.contents[0][0],
                                           fg='cyan'),
                                 clk.style(dbno1, fg='yellow'))

    if ntr.is_food(dbno2) or ntr.is_recipe(dbno2):
        nl2 = ntr.get_nutrients(dbno2)
        h2 = clk.style(dbno2, fg='magenta')
    else:
        nl2 = ntr.NutrientList(ntr.get_usda_nutrients(dbno2))
        h2 = '{} [{:5s}]'.format(clk.style(nl2.self.contents[0][0],
                                           fg='cyan'),
                                 clk.style(dbno2, fg='yellow'))

    out = mk_header('comparing at {} threshold'
                    .format(clk.style('{:3.1f}'.format(thr), fg='blue')))
    out += mk_header('{} {} {}'.format(h1, clk.style('vs'), h2))
    out += mk_header('values for {}'
                     .format(clk.style(str(int(amt)) + ' ' +
                                       ('kcal' if norm else 'g'),
                                       fg='yellow')))

    joint_keys = set(k for k in nl1.vals.keys()) |\
        set(k for k in nl2.vals.keys())
    vals1 = {k: (nl1.vals[k]/((nl1.vals['energy']/amt).val if norm else 1)
             if k in nl1.vals
             else ntr.Amount(0., nl2.vals[k].unit)) for k in joint_keys}
    vals2 = {k: (nl2.vals[k]/((nl2.vals['energy']/amt).val if norm else 1)
             if k in nl2.vals
             else ntr.Amount(0., nl1.vals[k].unit)) for k in joint_keys}

    cls1 = {k: ('green' if vals1[k] > thr*vals2[k] else
            ('red' if thr*vals1[k] < vals2[k] else 'yellow'))
            for k in joint_keys}
    cls2 = {k: ('green' if cls1[k] == 'red' else
            ('red' if cls1[k] == 'green' else 'yellow'))
            for k in joint_keys}
    itms = ['{: >40s}: {: >20s} | {: <20} {}'
            .format(k,
                    clk.style('{: >8.3f}'.format(vals1[k]
                                                 .convert(vals2[k].unit).val),
                              fg=cls1[k]),
                    clk.style('{: <8.3f}'.format(vals2[k].val),
                              fg=cls2[k]),
                    vals2[k].unit)
            for k in sorted(joint_keys, key=ntr.sort_nutrs)
            if not np.isclose(vals1[k].val + vals2[k].val, 0) and
            cls1[k] != 'yellow' and
            (not nz or (not np.isclose(vals1[k].val, 0) and
                        not np.isclose(vals2[k].val, 0)))]

    out += '\n'.join(itms)
    clk.echo_via_pager(out)


@clk.command()
@clk.argument('food')
@clk.argument('qty', nargs=1, required=False)
@clk.option('-t', nargs=1)
@clk.option('-d', nargs=1)
# TODO: generalized date handling
def eat(food, qty, **kwargs):
    lfn = get_logfn()
    with open(RCP_FN, 'r') as f:
        fd = yaml.load(f)
        if (food not in fd['recipes'] and
            food not in fd['alias'] and
            food not in fd['usda foods'] and
            food not in fd['custom foods']):
            clk.echo('"{}" not in recipes file!'
                     ' can\'t eat food we don\'t know!'
                     .format(clk.style(food, fg='yellow')))

    now = dtm.datetime.now()

    d = kwargs['d']
    if d is None:
        d = now.strftime('%d')
    else:
        d = '{:02d}'.format(int(d))
    t = kwargs['t']
    if t is None:
        t = now.strftime('%H:%M')

    tm = '{} {}'.format(d, t)

    logstr = '{} - {}'.format(tm, food)
    if qty:
        if qty.startswith('m'):
            qty = '-' + qty[1:]
        if qty.startswith('x'):
            qty = qty[1:]
        logstr += ' x{:4.2f}'.format(float(qty))
    logstr += '\n'

    open(lfn, 'a').close()
    with open(lfn, 'r') as f:
        lns = f.readlines()
        lns.append(logstr)
        lns = sorted(lns)
    out = ''.join(lns)

    with open(lfn, 'w') as f:
        f.write(out)


@clk.command()
@clk.argument('nutrs', nargs=-1, required=False)
@clk.option('--month')
@clk.option('-d', is_flag=True)
def review(nutrs, **kwargs):
    month = kwargs['month']
    delta = kwargs['d']
    lns = get_loglines(month)

    if month is None:
        month = dtm.datetime.now().isoformat()[:7]

    cfg = read_config()['reports']
    if not nutrs:
        line_nutrs = cfg['summary']
    elif len(nutrs) == 1 and nutrs[0] in cfg:
        line_nutrs = cfg[nutrs[0]]
    else:
        line_nutrs = nutrs
    goal = read_goal()
    min_amts = {k: ntr.Amount(v['min'], v.get('unit', 'g'))
                for k, v in goal.items() if 'min' in v}
    max_amts = {k: ntr.Amount(v['max'], v.get('unit', 'g'))
                for k, v in goal.items() if 'max' in v}

    out = mk_header('log for {}'.format(clk.style(month, fg='yellow')))
    out += ' '*40 + (' | '.join(['{: ^22s}' for _ in line_nutrs])
                          .format(*[clk.style(ln, fg='blue')
                                    for ln in line_nutrs]) + '\n')

    cur_day = lns[0][0]
    nl = ntr.NutrientList()
    nlg = ntr.NutrientList((goal, [(n, amt.val, amt.unit)
                            for n, amt in min_amts.items()]))
    for ln in lns:
        if ln[0] > cur_day:
            nl.balance()
            fd = {n: ('green'
                      if (n not in min_amts or amt > min_amts[n]) and
                      (n not in max_amts or amt < max_amts[n])
                      else ('magenta' if n in max_amts and amt > max_amts[n]
                            else 'red'))
                      for n, amt in nl.vals.items()}
            bd = {n: ('black'
                      if (n not in max_amts or amt < max_amts[n])
                      else 'black') for n, amt in nl.vals.items()}
            if delta:
                out += ('{:-^49s}'.format(clk.style('   GOAL   ', fg='green'))
                        + nlg.get_line(line_nutrs) + '\n')

            out += ('{:-^49s}'.format(clk.style('   {}   '
                                                .format('TOTAL' if not delta
                                                        else 'DELTA'),
                                                fg='red'))
                    + nl.get_line(line_nutrs, fg=fd, bg=bd,
                                  target=(min_amts if delta else None)))
            out += '\n\n'
            cur_day = ln[0]
            nl = ntr.NutrientList()

        mult = (float(ln[3]) if ln[3] else 1)

        sub_nl = mult * ntr.get_nutrients(ln[2])
        nl += sub_nl

        sub_out = 'day {}, {} - {}'.format(ln[0], ln[1], ln[2])
        if ln[3]:
            sub_out += ' x{}'.format(ln[3])
        sub_out += '   '
        out += '{:-<40s}'.format(sub_out) + sub_nl.get_line(line_nutrs,
                                                            fg=False)
        out += '\n'
    nl.balance()
    out += ('{:-^49s}'.format(clk.style('   SUBTOTAL   ', fg='red')) +
            nl.get_line(line_nutrs) + '\n')
    out += ('{:-^49s}'.format(clk.style('   GOAL   ', fg='green'))
            + nlg.get_line(line_nutrs) + '\n')
    out += '\n\n'

    clk.echo_via_pager(out)


@clk.command()
@clk.option('-m', nargs=1)
@clk.argument('file', nargs=1)
def edit(**kwargs):
    f = kwargs['file']
    if f is None:
        fn = get_logfn(kwargs['m'])
    if f is not None:
        f = f.lower()
        if f == 'recipe' or f == 'recipes':
            fn = RCP_FN
        elif f == 'goal' or f == 'goals':
            fn = GOAL_FN
        elif f == 'config':
            fn = CFG_FN
        else:
            fn = get_logfn(kwargs['m'])
            
    call([EDITOR, fn])


@clk.group()
def main():
    pass

main.add_command(find)
main.add_command(info)
main.add_command(compare)
main.add_command(eat)
main.add_command(review)
main.add_command(edit)

if __name__ == '__main__':
    # from pycallgraph import PyCallGraph
    # from pycallgraph.output import GraphvizOutput

    # with PyCallGraph(output=GraphvizOutput()):
    main()
