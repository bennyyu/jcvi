#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
%prog blastfile --qsizes query.sizes --ssizes subject.sizes

Visualize the blastfile in a dotplot. At least one of --qsizes and --qbed must
be specified, also at least one of --ssizes and --sbed. The --sizes options help
to define the molecule border as well as the drawing order. The --bed options
help to position names maker (e.g. genes) onto the dot plot. So depending on
whether you are BLASTing raw sequences or makers, you need to place --sizes or
--bed options.
"""

import os.path as op
import sys
import logging
from random import sample
from optparse import OptionParser

import numpy as np

from jcvi.formats.blast import BlastLine
from jcvi.formats.sizes import Sizes
from jcvi.formats.bed import Bed
from jcvi.apps.base import debug
from jcvi.graphics.base import plt, ticker, Rectangle, cm, _, \
        set_human_base_axis, set_image_options
debug()


DotStyles = ("line", "circle", "dot")


def rename_seqid(seqid):
    seqid = seqid.split("_")[-1]
    seqid = seqid.replace("contig", "c").replace("scaffold", "s")
    seqid = seqid.replace("supercont", "s")
    try:
        seqid = int(seqid)
        seqid = "c%d" % seqid
    except:
        pass
    return seqid


def blastplot(ax, blastfile, qsizes, ssizes, qbed, sbed,
        style="dot", proportional=False, sampleN=None,
        baseticks=False, insetLabels=False, stripNames=False,
        highlights=None):

    assert style in DotStyles
    fp = open(blastfile)

    qorder = qbed.order if qbed else None
    sorder = sbed.order if sbed else None

    data = []

    for row in fp:
        b = BlastLine(row)
        query, subject = b.query, b.subject

        if stripNames:
            query = query.rsplit(".", 1)[0]
            subject = subject.rsplit(".", 1)[0]

        if qorder:
            if query not in qorder:
                continue
            qi, q = qorder[query]
            query = q.seqid
            qstart, qend = q.start, q.end
        else:
            qstart, qend = b.qstart, b.qstop

        if sorder:
            if subject not in sorder:
                continue
            si, s = sorder[subject]
            subject = s.seqid
            sstart, send = s.start, s.end
        else:
            sstart, send = b.sstart, b.sstop

        qi = qsizes.get_position(query, qstart)
        qj = qsizes.get_position(query, qend)
        si = ssizes.get_position(subject, sstart)
        sj = ssizes.get_position(subject, send)

        if None in (qi, si):
            continue
        data.append(((qi, qj), (si, sj)))

    if sampleN:
        if len(data) > sampleN:
            data = sample(data, sampleN)

    if not data:
        return logging.error("no blast data imported")

    xsize, ysize = qsizes.totalsize, ssizes.totalsize
    logging.debug("xsize=%d ysize=%d" % (xsize, ysize))

    if style == "line":
        for a, b in data:
            ax.plot(a, b, 'ro-', mfc="w", mec="r", ms=3)
    else:
        data = [(x[0], y[0]) for x, y in data]
        x, y = zip(*data)

        if style == "circle":
            ax.plot(x, y, 'mo', mfc="w", mec="m", ms=3)
        elif style == "dot":
            ax.scatter(x, y, s=3, lw=0)

    xlim = (0, xsize)
    ylim = (ysize, 0)  # invert the y-axis

    xchr_labels, ychr_labels = [], []
    ignore = True  # tag to mark whether to plot chr name (skip small ones)
    #ignore_size_x = xsize * .02
    #ignore_size_y = ysize * .02
    ignore_size_x = ignore_size_y = 0

    # plot the chromosome breaks
    logging.debug("xbreaks={0} ybreaks={1}".format(len(qsizes), len(ssizes)))
    for (seqid, beg, end) in qsizes.get_breaks():
        ignore = abs(end - beg) < ignore_size_x
        if ignore:
            continue
        seqid = rename_seqid(seqid)

        xchr_labels.append((seqid, (beg + end) / 2, ignore))
        ax.plot([end, end], ylim, "-", lw=1, color="grey")

    for (seqid, beg, end) in ssizes.get_breaks():
        ignore = abs(end - beg) < ignore_size_y
        if ignore:
            continue
        seqid = rename_seqid(seqid)

        ychr_labels.append((seqid, (beg + end) / 2, ignore))
        ax.plot(xlim, [end, end], "-", lw=1, color="grey")

    # plot the chromosome labels
    for label, pos, ignore in xchr_labels:
        if not ignore:
            if insetLabels:
                ax.text(pos, 0, label, size=8, \
                    ha="center", va="top", color="grey")
            else:
                pos = .1 + pos * .8 / xsize
                root.text(pos, .91, label, size=10,
                    ha="center", va="bottom", rotation=45, color="grey")

    # remember y labels are inverted
    for label, pos, ignore in ychr_labels:
        if not ignore:
            if insetLabels:
                continue
            pos = .9 - pos * .8 / ysize
            root.text(.91, pos, label, size=10,
                    va="center", color="grey")

    # Highlight regions based on a list of BedLine
    if highlights:
        for hl in highlights:
            ax.add_patch(Rectangle((0, hl.start), xsize, hl.span, \
                         fc="r", alpha=.2, lw=0))

    if baseticks:
        def increaseDensity(a, ratio=4):
            assert len(a) > 1
            stepsize = a[1] - a[0]
            newstepsize = int(stepsize / ratio)
            return np.arange(0, a[-1], newstepsize)

        # Increase the density of the ticks
        xticks = ax.get_xticks()
        yticks = ax.get_yticks()
        xticks = increaseDensity(xticks, ratio=2)
        yticks = increaseDensity(yticks, ratio=2)
        ax.set_xticks(xticks)
        #ax.set_yticks(yticks)

        # Plot outward ticklines
        for pos in xticks[1:]:
            if pos > xsize:
                continue
            pos = .1 + pos * .8 / xsize
            root.plot((pos, pos), (.08, .1), '-', color="grey", lw=2)

        for pos in yticks[1:]:
            if pos > ysize:
                continue
            pos = .9 - pos * .8 / ysize
            root.plot((.09, .1), (pos, pos), '-', color="grey", lw=2)

    ax.set_xlim(xlim)
    ax.set_ylim(ylim)

    # beautify the numeric axis
    for tick in ax.get_xticklines() + ax.get_yticklines():
        tick.set_visible(False)

    set_human_base_axis(ax)

    plt.setp(ax.get_xticklabels() + ax.get_yticklabels(),
            color='gray', size=10)
    plt.setp(ax.get_yticklabels(), rotation=90)


if __name__ == "__main__":

    from jcvi.formats.bed import sizes

    p = OptionParser(__doc__)
    p.add_option("--qsizes", help="Path to two column qsizes file")
    p.add_option("--ssizes", help="Path to two column ssizes file")
    p.add_option("--qbed", help="Path to qbed")
    p.add_option("--sbed", help="Path to sbed")
    p.add_option("--qselect", default=0, type="int",
            help="Minimum size of query contigs to select [default: %default]")
    p.add_option("--sselect", default=0, type="int",
            help="Minimum size of subject contigs to select [default: %default]")
    p.add_option("--style", default="dot", choices=DotStyles,
            help="Style of the dots, one of {0} [default: %default]".\
                format("|".join(DotStyles)))
    p.add_option("--proportional", default=False, action="store_true",
            help="Make image width:height equal to seq ratio [default: %default]")
    p.add_option("--stripNames", default=False, action="store_true",
            help="Remove trailing .? from gene names [default: %default]")
    p.add_option("--sample", default=None, type="int",
            help="Only plot maximum of N dots [default: %default]")
    opts, args, iopts = set_image_options(p, figsize="8x8", dpi=150)

    qsizes, ssizes = opts.qsizes, opts.ssizes
    qbed, sbed = opts.qbed, opts.sbed
    proportional = opts.proportional

    if len(args) != 1:
        sys.exit(not p.print_help())

    if qbed:
        qsizes = qsizes or sizes([qbed])
        qbed = Bed(qbed)
    if sbed:
        ssizes = ssizes or sizes([sbed])
        sbed = Bed(sbed)

    assert qsizes and ssizes, \
        "You must specify at least one of --sizes of --bed"

    qsizes = Sizes(qsizes, select=opts.qselect)
    ssizes = Sizes(ssizes, select=opts.sselect)

    blastfile, = args

    image_name = op.splitext(blastfile)[0] + "." + opts.format
    plt.rcParams["xtick.major.pad"] = 16
    plt.rcParams["ytick.major.pad"] = 16

    # Fix the width
    xsize, ysize = qsizes.totalsize, ssizes.totalsize

    ratio = ysize * 1. / xsize if proportional else 1
    width = iopts.w
    height = iopts.h * ratio
    fig = plt.figure(1, (width, height))
    root = fig.add_axes([0, 0, 1, 1])  # the whole canvas
    ax = fig.add_axes([.1, .1, .8, .8])  # the dot plot

    blastplot(ax, blastfile, qsizes, ssizes, qbed, sbed,
            style=opts.style, proportional=proportional, sampleN=opts.sample,
            baseticks=True, stripNames=opts.stripNames)

    # add genome names
    to_ax_label = lambda fname: _(op.basename(fname).split(".")[0])
    gx, gy = [to_ax_label(x.filename) for x in (qsizes, ssizes)]
    ax.set_xlabel(gx, size=16)
    ax.set_ylabel(gy, size=16)

    root.set_xlim(0, 1)
    root.set_ylim(0, 1)
    root.set_axis_off()
    logging.debug("Print image to `{0}` {1}".format(image_name, iopts))
    plt.savefig(image_name, dpi=iopts.dpi)
    plt.rcdefaults()
