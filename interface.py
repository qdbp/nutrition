#! /usr/bin/python
import click as clk
from collections import defaultdict
import datetime as dtm
import numpy as np
import os.path as osp
import re
import time

import yaml

RE_ANSI = re.compile(r'(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]')
RE_LOG = re.compile(r'^([0-9]{2}) ([0-9]{2}:[0-9]{2}) - (.*?)(?:$| x(.*?)$)')

CONFIG_PATH = osp.join(osp.expanduser('~'), '.config/nutrition/')
CFG_FN = osp.join(CONFIG_PATH, 'config.yaml')
RCP_FN = osp.join(CONFIG_PATH, 'recipes.yaml')

import nutrients as ntr


def get_logfn(month=None):
    LOG_FN = osp.join(CONFIG_PATH, '{}-log.txt')
    if month is None:
        month = dtm.datetime.now().isoformat()[:7]
    return LOG_FN.format(month)


def mk_header(s, pad=100):
    l = len(s)
    ls = len(RE_ANSI.sub('', s))
    s = '{0:=^{1}}'.format(' ' + s + ' ', pad+l-ls) + '\n'
    return s


def get_loglines(month=None):
    with open(get_logfn(month), 'r') as f:
        lines = list(f.readlines())
    print(lines)
    return [RE_LOG.findall(line)[0] for line in lines if line]

STR_G = mk_header('values for {}'.format(clk.style('{} g', fg='red')))


@clk.command()
@clk.argument('name')
def find(name):
    j = ntr.lookup_food(name)
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
@clk.argument('dbno', nargs=1)
@clk.argument('amount', nargs=1, required=False)
@clk.option('-a', is_flag=True, default=False)
def info(dbno, **kwargs):
    amount = int(kwargs['amount'])
    adv = kwargs['a']
    if amount is None:
        amount = 100

    name, info = ntr.fetch_nutrients(dbno, advanced=bool(adv))
    out = 'looking up [{:5s}] {}'.format(clk.style(str(dbno), fg='yellow'),
                                         clk.style(name, fg='cyan'))

    out = mk_header(out)
    out += STR_G.format(int(amount))
    itms = ['{: >40s}: {: >10s} {}'.format(n,
                                           clk.style('{: 8.3f}'
                                                     .format(v*amount/100),
                                                     fg='yellow'),
                                           u)
            for n, v, u in info if not np.isclose(v, 0)]
    out += '\n'.join(itms)
    clk.echo(out)


@clk.command()
@clk.argument('dbno1', nargs=1, required=True)
@clk.argument('dbno2', nargs=1, required=True)
@clk.option('-a', is_flag=True, default=False)
def compare(dbno1, dbno2, **kwargs):
    adv = kwargs['a']
    n1, i1 = ntr.fetch_nutrients(dbno1, advanced=adv)
    n2, i2 = ntr.fetch_nutrients(dbno2, advanced=adv)
    out = mk_header('comparing')
    out += mk_header('{} [{:5s}] {} [{:5s}] {}'
                     .format(clk.style(n1, fg='cyan'),
                             clk.style(dbno1, fg='yellow'),
                             clk.style('vs', fg='red'),
                             clk.style(dbno2, fg='yellow'),
                             clk.style(n2, fg='cyan')))
    out += STR_G.format(100)
    # TODO: this is a fucking mess
    nuts = sorted(set(n for n, v, u in i1) | set(n for n, v, u in i2))
    d1 = dict((n, (v, u)) for n, v, u in i1)
    d2 = dict((n, (ntr.uconv(u, d1.get(n, (0, ''))[1])*v, u))
              for n, v, u in i2)

    vals = {n: (d1.get(n, (0,))[0], d2.get(n, (0,))[0]) for n in nuts}
    cmps = {n: (-1 if 1.05*v1 < v2 else (1 if v1 > 1.05*v2 else 0))
            for n, (v1, v2) in vals.items() if not (np.isclose(v1, 0) and
                                                    np.isclose(v2, 0))}
    ks = list(vals.keys())
    for k in ks:
        if k not in cmps:
            vals.pop(k)
    cls1 = {-1: 'red', 0: 'white', 1: 'green'}
    cls2 = {-1: 'green', 0: 'white', 1: 'red'}

    itms = ['{: >40s}: {: >20s} | {: <20} {}'
            .format(n,
                    clk.style('{: >8.3f}'.format(v1), fg=cls1[cmps[n]]),
                    clk.style('{: <8.3f}'.format(v2), fg=cls2[cmps[n]]),
                    d1.get(n, d2[n])[1])
            for n, (v1, v2) in sorted(vals.items())]
    out += '\n'.join(itms)
    clk.echo(out)


@clk.command()
@clk.argument('food')
@clk.argument('qty', nargs=1, required=False)
@clk.option('-t', nargs=1)
@clk.option('-d', nargs=1)
# TODO: generalized date handling
def eat(food, qty, **kwargs):
    lfn = get_logfn()
    with open(RCP_FN, 'r') as f:
        if food not in yaml.load(f)['recipes']:
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
        logstr += ' x{:3.1f}'.format(float(qty))
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
@clk.option('--month')
def review(**kwargs):
    month = kwargs['month']
    lns = get_loglines(month)

    if month is None:
        month = dtm.datetime.now().isoformat()[:7]

    out = mk_header('log for {}'.format(clk.style(month, fg='yellow')))
    cur_day = lns[0][0]
    for ln in lns:
        if ln[0] > cur_day:
            out += '\n'
            cur_day = ln[0]
        out += 'day {}, {} - {}'.format(ln[0], ln[1], ln[2])
        if ln[3]:
            out += ' x{}'.format(ln[3])
        out += '\n'

    clk.echo_via_pager(out)



@clk.group()
def main():
    pass
main.add_command(find)
main.add_command(info)
main.add_command(compare)
main.add_command(eat)
main.add_command(review)

if __name__ == '__main__':
    main()
