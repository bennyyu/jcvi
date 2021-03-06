#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
Simulate fake reads from genome for benchmarking.
"""

import sys
import logging

from optparse import OptionParser

from jcvi.formats.fasta import Fasta
from jcvi.apps.base import ActionDispatcher, debug, sh
debug()


def main():

    actions = (
        ('wgsim', 'sample paired end reads using dwgsim'),
            )
    p = ActionDispatcher(actions)
    p.dispatch(globals())


def wgsim(args):
    """
    %prog wgsim fastafile

    Run dwgsim on fastafile.
    """
    p = OptionParser(wgsim.__doc__)
    p.add_option("--erate", default=.02, type="float",
                 help="Base error rate of the read [default: %default]")
    p.add_option("--distance", default=500, type="int",
                 help="Outer distance between the two ends [default: %default]")
    p.add_option("--genomesize", type="int",
                 help="Genome size in Mb [default: estimate from data]")
    p.add_option("--depth", default=10, type="int",
                 help="Target depth (aka base coverage) [default: %default]")
    p.add_option("--readlen", default=100, type="int",
                 help="Length of the read [default: %default]")
    p.add_option("--noerrors", default=False, action="store_true",
                 help="Simulate reads with no errors [default: %default]")
    opts, args = p.parse_args(args)

    if len(args) != 1:
        sys.exit(not p.print_help())

    fastafile, = args
    pf = fastafile.split(".")[0]

    size = opts.genomesize * 1000000 or Fasta(fastafile).totalsize
    depth = opts.depth
    readlen = opts.readlen
    readnum = size * depth / (2 * readlen)

    distance = opts.distance
    stdev = distance / 5

    outpf = "{0}.{1}bp.{2}x".format(pf, distance, depth)
    distance -= 2 * readlen  # Outer distance => Inner distance
    assert distance >= 0, "Outer distance must be >= 2 * readlen"

    logging.debug("Total genome size: {0} bp".format(size))
    logging.debug("Target depth: {0}x".format(depth))
    logging.debug("Number of read pairs (2x{0}): {1}".format(readlen, readnum))

    if opts.noerrors:
        opts.erate = 0

    cmd = "dwgsim -e {0} -E {0}".format(opts.erate)
    if opts.noerrors:
        cmd += " -r 0 -R 0 -X 0 -y 0"

    cmd += " -d {0} -s {1}".format(distance, stdev)
    cmd += " -N {0} -1 {1} -2 {1}".format(readnum, readlen)
    cmd += " {0} {1}".format(fastafile, outpf)
    sh(cmd)


if __name__ == '__main__':
    main()
