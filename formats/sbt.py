#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
GenBank submission template. In nested blocks below.
"""

import csv
import sys
import string
import logging

from optparse import OptionParser

from jcvi.apps.base import ActionDispatcher, debug
debug()

NameTemplate = """        {{
          name name {{
            last "{last}",
            first "{first}",
            initials "{initials}",
            suffix "{suffix}"
          }}
        }}"""


class SubmissionTemplate (object):
    def __init__(self):
        raise NotImplementedError


def main():

    actions = (
        ('names', 'convert a list of names to sbt blocks'),
            )
    p = ActionDispatcher(actions)
    p.dispatch(globals())


def get_name_parts(au):
    """
    Fares Z. Najar => last, first, initials

    >>> get_name_parts("Fares Z. Najar")
    ('Najar', 'Fares', 'F.Z.')
    """
    parts = au.split()
    first = parts[0]
    middle = [x for x in parts if x[-1] == '.']
    middle = "".join(middle)

    last = [x for x in parts[1:] if x[-1] != '.']
    last = " ".join(last)
    initials = "{0}.{1}".format(first[0], middle)
    if first[-1] == '.':  # Some people use full middle name
        middle, last = last.split(None, 1)
        initials = "{0}.{1}.".format(first[0], middle)

    return last, first, initials


def parse_names(lstfile):
    """
    This is the alternative format `lstfile`. In this format, there are two
    sections, starting with [Sequence] and [Manuscript], respectively, then
    followed by authors separated by comma.
    """
    import string
    from jcvi.formats.base import read_block

    fp = open(lstfile)
    all_authors = []
    for header, seq in read_block(fp, "["):
        seq = " ".join(seq)
        authors = []
        for au in seq.split(","):
            au = au.strip()
            if not au:
                continue
            au = string.translate(au, None, string.digits)
            #au = au.replace("-", '')
            authors.append(au)
        all_authors.append(authors)

    out = []
    for authors in all_authors:
        blocks = []
        for au in authors:
            last, first, initials = get_name_parts(au)
            suffix = ""
            nameblock = NameTemplate.format(last=last, first=first,
                    initials=initials, suffix=suffix)
            blocks.append(nameblock)
        bigblock = ",\n".join(blocks)
        out.append(bigblock)

    return out


def make_template(templatefile, out):
    template = open(templatefile).read()
    template = string.Template(template)
    outmapping = dict(("N{0}".format(i), x) for (i, x) in enumerate(out))
    t = template.substitute(outmapping)
    print t


def names(args):
    """
    %prog names namelist templatefile

    Generate name blocks from the `namelist` file. The `namelist` file is
    tab-delimited that contains >=4 columns of data. 
    
    Three columns are mandatory. First name, middle initial and last name.
    First row is table header.

    For the extra columns, the first column will go in the `$N0` field
    in the template file, second to the `$N1` field, etc.

    In the alternative format, the namelist just contains two sections. First
    row will go in the `$N0` in the template file, second to the `$N1` field.
    """
    p = OptionParser(names.__doc__)
    opts, args = p.parse_args(args)

    if len(args) != 2:
        sys.exit(p.print_help())

    namelist, templatefile = args

    # First check the alternative format
    if open(namelist).read()[0] == '[':
        out = parse_names(namelist)
        make_template(templatefile, out)
        return

    reader = csv.reader(open(namelist), delimiter="\t")
    header = reader.next()
    ncols = len(header)
    assert ncols > 3
    nextras = ncols - 3

    blocks = []
    bools = []
    for row in reader:
        first, middle, last = row[:3]
        extras = row[3:]
        bools.append([(x.upper() == 'Y') for x in extras])
        middle = middle.strip()
        if middle != "":
            middle = middle.rstrip('.') + '.'
        initials = "{0}.{1}".format(first[0], middle)
        suffix = ""
        nameblock = NameTemplate.format(last=last, first=first,
                initials=initials, suffix=suffix)
        blocks.append(nameblock)

    selected_idx = zip(*bools)
    out = [] * nextras
    for i, sbools in enumerate(selected_idx):
        selected = []
        for b, ss in zip(blocks, sbools):
            if ss:
                selected.append(b)
        bigblock = ",\n".join(selected)
        out.append(bigblock)
        logging.debug("List N{0} contains a total of {1} names.".format(i,
            len(selected)))

    make_template(templatefile, out)


if __name__ == '__main__':
    import doctest
    doctest.testmod()

    main()
