#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
Based on read pair mappings, construct contig graph
"""

import sys
import logging

from collections import defaultdict
from optparse import OptionParser

from jcvi.formats.base import must_open
from jcvi.formats.bed import BedLine, pairs
from jcvi.formats.sizes import Sizes
from jcvi.utils.iter import pairwise
from jcvi.apps.base import ActionDispatcher, debug
debug()


class LinkLine (object):

    def __init__(self, row):
        args = row.split()
        # MKDU973T  mte1-26c10_002  mte1-26c10_011  +-  5066  23563
        self.mate = args[0]
        self.aseqid = args[1]
        self.bseqid = args[2]
        self.orientation = args[3]
        self.insert = int(args[4])
        self.distance = int(args[5])


class ContigLink (object):

    def __init__(self, a, b, insert=3000, cutoff=6000):
        assert isinstance(a, BedLine) and isinstance(b, BedLine)
        self.a = a
        self.b = b
        self.insert = insert
        assert self.insert > 0

        self.cutoff = cutoff
        assert self.cutoff > self.insert

    def __str__(self):
        aseqid = self.a.seqid.rstrip("-")
        bseqid = self.b.seqid.rstrip("-")
        return "\t".join(str(x) for x in (aseqid, bseqid,
            self.orientation, self.insert, self.distance))

    def get_orientation(self, aseqid, bseqid):
        """
        Determine N/A/I/O from the names.
        """
        ta = '-' if aseqid[-1] == '-' else '+'
        tb = '-' if bseqid[-1] == '-' else '+'
        pair = ta + tb
        assert pair in ('++', '--', '+-', '-+')

        return pair

    def flip_innie(self, sizes, debug=False):
        """
        The algorithm that determines the oNo of this contig pair, the contig
        order is determined by +-, assuming that the matepairs are `innies`. In
        below, we determine the order and orientation by flipping if necessary,
        bringing the strandness of two contigs to the expected +-.

        sizes: the contig length dictionary Sizes().
        """
        a, b = self.a, self.b
        Pa, Pb = a.start - 1, b.start - 1
        Ea, Eb = a.end, b.end

        if a.strand == b.strand:
            if b.strand == "+":  # case: "++", flip b
                b.reverse_complement(sizes)
            else:  # case: "--", flip a
                a.reverse_complement(sizes)

        if b.strand == "+":  # case: "-+"
            a, b = b, a
            Pa, Pb = Pb, Pa
            Ea, Eb = Eb, Ea

        assert a.strand == "+" and b.strand == "-"
        """
        ------===----          -----====----
              |_ahang            bhang_|
        """
        aseqid = a.seqid.rstrip('-')
        size = sizes.get_size(aseqid)
        ahang = size - a.start + 1
        bhang = b.end

        if debug:
            print >> sys.stderr, '*' * 60
            print >> sys.stderr, a
            print >> sys.stderr, b
            print >> sys.stderr, "ahang={0} bhang={1}".format(ahang, bhang)

        # Valid links need to be separated by the lib insert
        hangs = ahang + bhang
        if hangs > self.cutoff:
            if debug:
                print >> sys.stderr, "invalid link ({0}).".format(hangs)
            return False

        pair = self.get_orientation(a.seqid, b.seqid)

        insert = self.insert
        if pair == "++":    # Normal
            distance = insert + Pa - Eb
        elif pair == "--":  # Anti-normal
            distance = insert - Ea + Pb
        elif pair == "+-":  # Innie
            distance = insert + Pa + Pb
        elif pair == "-+":  # Outie
            distance = insert - Ea - Eb

        # Pair (1+, 2-) is the same as (2+, 1-), only do the canonical one
        if a.seqid > b.seqid:
            a.reverse_complement(sizes)
            b.reverse_complement(sizes)
            a, b = b, a

        self.a, self.b = a, b
        self.distance = distance
        self.orientation = self.get_orientation(a.seqid, b.seqid)

        return True


def main():

    actions = (
        ('link', 'construct links from bed file'),
        ('bundle', 'bundle multiple links into contig edges'),
        ('scaffold', 'build scaffold AGP using links/bundles'),
        ('query', 'query the path between given contigs from the bundle'),
            )
    p = ActionDispatcher(actions)
    p.dispatch(globals())


def query(args):
    """
    %prog query bundlefile sourcectg targetctg

    Query the path from sourcectg to targetctg using links in the bundlefile.
    """
    from jcvi.algorithms.graph import nx, shortest_path

    p = OptionParser(query.__doc__)

    opts, args = p.parse_args(args)

    if len(args) < 3:
        sys.exit(not p.print_help())

    bundlefile, srcctg, targetctg = args

    g = nx.MultiGraph()
    fp = open(bundlefile)
    for row in fp:
        # 5  contig_12167  contig_43478  -+  0  -664
        c = LinkLine(row)
        g.add_edge(c.aseqid, c.bseqid)

    ctgs = shortest_path(g, srcctg, targetctg)

    ctgs = set(ctgs)
    fp = open(bundlefile)
    for row in fp:
        c = LinkLine(row)
        if c.aseqid in ctgs and c.bseqid in ctgs:
            print row.rstrip()


def bundle(args):
    """
    %prog bundle linkfiles

    Bundle contig links into high confidence contig edges. This is useful to
    combine multiple linkfiles (from different libraries).
    """
    import numpy as np

    p = OptionParser(bundle.__doc__)
    p.add_option("--links", type="int", default=1,
            help="Minimum number of mate pairs to bundle [default: %default]")
    opts, args = p.parse_args(args)

    if len(args) < 1:
        sys.exit(not p.print_help())

    fp = must_open(args)
    contigGraph = defaultdict(list)
    for row in fp:
        c = LinkLine(row)
        contigGraph[(c.aseqid, c.bseqid)].append((c.orientation, c.distance))

    for (aseqid, bseqid), distances in contigGraph.items():
        # For the same pair of contigs, their might be conflicting orientations
        # or distances. Only keep the one with the most pairs.
        m = defaultdict(list)
        for orientation, dist in distances:
            m[orientation].append(dist)

        orientation, distances = max(m.items(), key=lambda x: len(x[1]))

        mates = len(distances)
        if mates < opts.links:
            continue

        distance = int(np.median(distances))
        print "\t".join(str(x) for x in \
                (mates, aseqid, bseqid, orientation, 0, distance))


def link(args):
    """
    %prog link bedfile fastafile

    Construct contig links based on bed file. Use --prefix to limit the links
    between contigs that start with the same prefix_xxx.
    """
    p = OptionParser(link.__doc__)
    p.add_option("--insert", type="int", default=0,
            help="Mean insert size [default: estimate from data]")
    p.add_option("--cutoff", type="int", default=0,
            help="Largest distance expected for linkage " + \
                 "[default: estimate from data]")
    p.add_option("--prefix", default=False, action="store_true",
            help="Only keep links between IDs with same prefix [default: %default]")
    p.add_option("--debug", dest="debug", default=False, action="store_true",
            help="Print verbose info when checking mates [default: %default]")
    opts, args = p.parse_args(args)

    if len(args) != 2:
        sys.exit(not p.print_help())

    bedfile, fastafile = args
    debug = opts.debug
    cutoff = opts.cutoff

    sizes = Sizes(fastafile)

    cutoffopt = "--cutoff={0}".format(cutoff)
    mateorientationopt = '--mateorientation=+-'
    bedfile, (meandist, stdev, p0, p1, p2) = \
            pairs([bedfile, cutoffopt, mateorientationopt])

    maxcutoff = cutoff or p2
    insert = opts.insert or p0
    logging.debug("Mate hangs must be <= {0}, --cutoff to override".\
            format(maxcutoff))

    rs = lambda x: x.accn[:-1]

    fp = open(bedfile)
    linksfile = bedfile.rsplit(".", 1)[0] + ".links"
    fw = open(linksfile, "w")

    for a, b in pairwise(fp):
        """
        Criteria for valid contig edge
        1. for/rev do not mapping to the same scaffold (useful for linking)
        2. assuming innie (outie must be flipped first), order the contig pair
        3. calculate sequence hangs, valid hangs are smaller than insert size
        """
        a, b = BedLine(a), BedLine(b)

        if rs(a) != rs(b):
            continue
        pe = rs(a)

        # Intra-contig links
        if a.seqid == b.seqid:
            continue

        # Use --prefix to limit the links between seqids with the same prefix
        # For example, contigs of the same BAC, mth2-23j10_001, mth-23j10_002
        if opts.prefix:
            aprefix = a.seqid.split("_")[0]
            bprefix = b.seqid.split("_")[0]
            if aprefix != bprefix:
                continue

        cl = ContigLink(a, b, insert=insert, cutoff=maxcutoff)
        if cl.flip_innie(sizes, debug=debug):
            print >> fw, "\t".join((pe, str(cl)))


def scaffold(args):
    """
    %prog scaffold ctgfasta linksfile

    Use the linksfile to build scaffolds. The linksfile can be
    generated by calling assembly.bundle.link() or assembly.bundle.bundle().
    Use --prefix to place the sequences with same prefix together. The final
    product is an AGP file.
    """
    from jcvi.algorithms.graph import nx
    from jcvi.formats.agp import order_to_agp

    p = OptionParser(scaffold.__doc__)
    p.add_option("--prefix", default=False, action="store_true",
            help="Keep IDs with same prefix together [default: %default]")
    opts, args = p.parse_args(args)

    if len(args) != 2:
        sys.exit(not p.print_help())

    ctgfasta, linksfile = args
    sizes = Sizes(ctgfasta).mapping
    logfile = "scaffold.log"
    fwlog = open(logfile, "w")

    pf = ctgfasta.rsplit(".", 1)[0]
    agpfile = pf + ".agp"
    fwagp = open(agpfile, "w")

    clinks = []
    g = nx.MultiGraph()  # use this to get connected components

    fp = open(linksfile)
    for row in fp:
        c = LinkLine(row)
        distance = max(c.distance, 50)

        g.add_edge(c.aseqid, c.bseqid,
                orientation=c.orientation, distance=distance)

    def get_bname(sname, prefix=False):
        return sname.rsplit("_", 1)[0] if prefix else "chr0"

    scaffoldbuckets = defaultdict(list)
    seqnames = sorted(sizes.keys())

    for h in nx.connected_component_subgraphs(g):
        partialorder = solve_component(h, sizes, fwlog)
        name = partialorder[0][0]
        bname = get_bname(name, prefix=opts.prefix)
        scaffoldbuckets[bname].append(partialorder)

    ctgbuckets = defaultdict(set)
    for name in seqnames:
        bname = get_bname(name, prefix=opts.prefix)
        ctgbuckets[bname].add(name)

    # Now the buckets contain a mixture of singletons and partially resolved
    # scaffolds. Print the scaffolds first then remaining singletons.
    scafname = "{0}.scf_{1:04d}"
    for bname, ctgs in sorted(ctgbuckets.items()):
        scaffolds = scaffoldbuckets[bname]
        scaffolded = set()
        ctgorder = []
        for scafID, scaf in enumerate(scaffolds):
            ctgorder = []
            for node, start, end, orientation in scaf:
                ctgorder.append((node, orientation))
                scaffolded.add(node)
            scaf = scafname.format(bname, scafID)
            order_to_agp(scaf, ctgorder, sizes, fwagp)
        singletons = sorted(ctgbuckets[bname] - scaffolded)
        nscaffolds = len(scaffolds)
        nsingletons = len(singletons)

        msg = "{0}: Scaffolds={1} Singletons={2}".\
            format(bname, nscaffolds, nsingletons)
        print >> sys.stderr, msg

        for singleton in singletons:
            ctgorder = [(singleton, "+")]
            order_to_agp(singleton, ctgorder, sizes, fwagp)

    fwagp.close()
    logging.debug("AGP file written to `{0}`.".format(agpfile))


def solve_component(h, sizes, fwlog):
    """
    Solve the component first by orientations, then by positions.
    """
    from jcvi.algorithms.matrix import determine_signs, determine_positions
    from jcvi.assembly.base import orientationflips

    nodes, edges = h.nodes(), h.edges(data=True)
    nodes = sorted(nodes)
    inodes = dict((x, i) for i, x in enumerate(nodes))

    # Solve signs
    ledges = []
    for a, b, c in edges:
        orientation = c["orientation"]
        orientation = '+' if orientation[0] == orientation[1] else '-'
        a, b = inodes[a], inodes[b]
        if a > b:
            a, b = b, a

        ledges.append((a, b, orientation))

    N = len(nodes)
    print >> fwlog, N, ", ".join(nodes)

    signs = determine_signs(nodes, ledges)
    print >> fwlog, signs

    # Solve positions
    dedges = []
    for a, b, c in edges:
        orientation = c["orientation"]
        distance = c["distance"]
        a, b = inodes[a], inodes[b]
        if a > b:
            a, b = b, a

        ta = '+' if signs[a] > 0 else '-'
        tb = '+' if signs[b] > 0 else '-'
        pair = ta + tb

        if orientationflips[orientation] == pair:
            distance = - distance
        elif orientation != pair:
            continue

        dedges.append((a, b, distance))

    positions = determine_positions(nodes, dedges)
    print >> fwlog, positions

    bed = []
    for node, sign, position in zip(nodes, signs, positions):
        size = sizes[node]
        if sign < 0:
            start = position - size
            end = position
            orientation = "-"
        else:
            start = position
            end = position + size
            orientation = "+"
        bed.append((node, start, end, orientation))

    key = lambda x: x[1]
    offset = key(min(bed, key=key))
    bed.sort(key=key)
    for node, start, end, orientation in bed:
        start -= offset
        end -= offset
        print >> fwlog, "\t".join(str(x) for x in \
                (node, start, end, orientation))

    return bed


if __name__ == '__main__':
    main()
