#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
Gradient gene features
"""

import os.path as op
import sys
import logging

from optparse import OptionParser

import numpy as np
from jcvi.apps.base import ActionDispatcher, debug
from jcvi.graphics.base import plt, Rectangle, CirclePolygon, Polygon, _
debug()

tstep = .05
Timing = np.arange(0, 1 + tstep, tstep)
arrowprops = dict(arrowstyle="fancy", fc="k", alpha=.5,
            connectionstyle="arc3,rad=-0.05")


class Bezier (object):
    """
    Cubic bezier curve, see the math:
    <http://www.moshplant.com/direct-or/bezier/math.html>
    p0 : origin, p1, p2 :control, p3: destination
    """
    def __init__(self, ax, p0, p1, p2, p3, color='m', alpha=.2):
        pts = (p0, p1, p2, p3)
        px, py = zip(*pts)
        xt = self.get_array(px)
        yt = self.get_array(py)

        ax.plot(xt, yt, "-", color=color, alpha=alpha)

    def get_array(self, pts, t=Timing):
        p0, p1, p2, p3 = pts

        # Get the coeffiencients
        c = 3 * (p1 - p0)
        b = 3 * (p2 - p1) - c
        a = p3 - p0 - c - b

        tsquared = t ** 2
        tcubic = tsquared * t
        return a * tcubic + b * tsquared + c * t + p0


class RoundLabel (object):
    """Round rectangle around the text label
    """
    def __init__(self, ax, x1, x2, t, **kwargs):

        ax.text(x1, x2, _(t), ha="center",
            bbox=dict(boxstyle="round",fill=False))


class DoubleCircle (object):
    """Circle with a double-line margin
    """
    def __init__(self, ax, x, y, radius=.01, **kwargs):

      ax.add_patch(CirclePolygon((x, y), radius * 1.4,
          resolution=50, fc="w", ec="k"))
      ax.add_patch(CirclePolygon((x, y), radius,
          resolution=50, **kwargs))


class TextCircle (object):
    """Circle with a character wrapped in
    """
    def __init__(self, ax, x, y, label, radius=.02, fc="k", color="w"):
        circle = CirclePolygon((x, y), radius, resolution=20, fc=fc, ec=fc)
        ax.add_patch(circle)
        ax.text(x, y, label, ha="center", va="center", color=color)


class Glyph (object):
    """Draws gradient rectangle
    """
    def __init__(self, ax, x1, x2, y, height=.03, fc="gray", **kwargs):

        width = x2 - x1
        # Frame around the gradient rectangle
        p1 = (x1, y - .5 * height)
        ax.add_patch(Rectangle(p1, width, height, fc=fc,
            lw=0, **kwargs))
        # Several overlaying patches
        for cascade in np.arange(.1, .55, .05):
            p1 = (x1, y - height * cascade)
            ax.add_patch(Rectangle(p1, width, 2 * cascade * height,
                fc='w', lw=0, alpha=.1))


class ExonGlyph (object):
    """Multiple rectangles linked together.
    """
    def __init__(self, ax, x, y, mrnabed, exonbeds, height=.03, ratio=1,
                 align="left", **kwargs):

        start, end = mrnabed.start, mrnabed.end
        xa = lambda a: x + (a - start) * ratio
        xb = lambda a: x - (end - a) * ratio
        xc = xa if align == "left" else xb

        Glyph(ax, xc(start), xc(end), y, height=height / 3)
        for b in exonbeds:
            bstart, bend = b.start, b.end
            Glyph(ax, xc(bstart), xc(bend), y, fc="orange")


class GeneGlyph (object):
    """Draws an oriented gene symbol, with color gradient, to represent genes
    """
    def __init__(self, ax, x1, x2, y, height, tip=.0025, **kwargs):
        # Figure out the polygon vertices first
        orientation = 1 if x1 < x2 else -1
        level = 10
        # Frame
        p1 = (x1, y - height * .5)
        p2 = (x2 - orientation * tip, y - height * .5)
        p3 = (x2, y)
        p4 = (x2 - orientation * tip, y + height * .5)
        p5 = (x1, y + .5*height)
        ax.add_patch(Polygon([p1, p2, p3, p4, p5], ec='k', **kwargs))

        zz = kwargs.get("zorder", 1)
        zz += 1
        # Patch (apply white mask)
        for cascade in np.arange(0, .5, .5 / level):
            p1 = (x1, y - height * cascade)
            p2 = (x2 - orientation * tip, y - height * cascade)
            p3 = (x2, y)
            p4 = (x2 - orientation * tip, y + height * cascade)
            p5 = (x1, y + height * cascade)
            ax.add_patch(Polygon([p1, p2, p3, p4, p5], fc='w', \
                    lw=0, alpha=.2, zorder=zz))


def main():

    actions = (
        ('demo', 'run a demo to showcase some common usages of various glyphs'),
        ('gff', 'draw exons for genes based on gff files'),
            )
    p = ActionDispatcher(actions)
    p.dispatch(globals())


def get_cds_beds(gffile, noUTR=False):
    from jcvi.formats.gff import Gff

    mrnabed = None
    cdsbeds = []
    gf = Gff(gffile)
    for g in gf:
        if g.type == "mRNA":
            mrnabed = g.bedline
        elif g.type == "CDS":
            cdsbeds.append(g.bedline)

    if noUTR:
        mrnabed.start = min(x.start for x in cdsbeds)
        mrnabed.end = max(x.end for x in cdsbeds)

    return mrnabed, cdsbeds


def get_setups(gffiles, canvas=.6, noUTR=False):
    setups = []
    for gffile in gffiles:
        genename = op.basename(gffile).rsplit(".", 1)[0]
        mrnabed, cdsbeds = get_cds_beds(gffile, noUTR=noUTR)
        setups.append((genename, mrnabed, cdsbeds))

    genenames, mrnabeds, cdsbedss = zip(*setups)
    maxspan = max(x.span for x in mrnabeds)
    ratio = canvas / maxspan
    return setups, ratio


def gff(args):
    """
    %prog gff *.gff

    Draw exons for genes based on gff files. Each gff file should contain only
    one gene, and only the "mRNA" and "CDS" feature will be drawn on the canvas.
    """
    align_choices = ("left", "center", "right")

    p = OptionParser(gff.__doc__)
    p.add_option("--align", default="left", choices=align_choices,
                 help="Horizontal alignment {0} [default: %default]".\
                    format("|".join(align_choices)))
    p.add_option("--noUTR", default=False, action="store_true",
                 help="Do not plot UTRs [default: %default]")
    opts, args = p.parse_args(args)

    if len(args) < 1:
        sys.exit(not p.print_help())

    fig = plt.figure(1, (8, 5))
    root = fig.add_axes([0, 0, 1, 1])

    gffiles = args
    ngenes = len(gffiles)

    setups, ratio = get_setups(gffiles, canvas=.6, noUTR=opts.noUTR)
    align = opts.align
    xs = .2 if align == "left" else .8
    yinterval = canvas / ngenes
    ys = .8
    tip = .01
    for genename, mrnabed, cdsbeds in setups:
        ex = ExonGlyph(root, xs, ys, mrnabed, cdsbeds, ratio=ratio, align=align)
        genename = _(genename)
        if align == "left":
            root.text(xs - tip, ys, genename, ha="right", va="center")
        elif align == "right":
            root.text(xs + tip, ys, genename, ha="left", va="center")
        ys -= yinterval

    root.set_xlim(0, 1)
    root.set_ylim(0, 1)
    root.set_axis_off()

    figname = "exons.pdf"
    plt.savefig(figname, dpi=300)
    logging.debug("Figure saved to `{0}`".format(figname))


def demo(args):
    """
    %prog demo

    Draw sample gene features to illustrate the various fates of duplicate
    genes - to be used in a book chapter.
    """
    p = OptionParser(demo.__doc__)
    opts, args = p.parse_args(args)

    fig = plt.figure(1, (8, 5))
    root = fig.add_axes([0, 0, 1, 1])

    panel_space = .23
    dup_space = .025
    # Draw a gene and two regulatory elements at these arbitrary locations
    locs = [(.5, .9), # ancestral gene
            (.5, .9 - panel_space + dup_space), # identical copies
            (.5, .9 - panel_space - dup_space),
            (.5, .9 - 2 * panel_space + dup_space), # degenerate copies
            (.5, .9 - 2 * panel_space - dup_space),
            (.2, .9 - 3 * panel_space + dup_space), # sub-functionalization
            (.2, .9 - 3 * panel_space - dup_space),
            (.5, .9 - 3 * panel_space + dup_space), # neo-functionalization
            (.5, .9 - 3 * panel_space - dup_space),
            (.8, .9 - 3 * panel_space + dup_space), # non-functionalization
            (.8, .9 - 3 * panel_space - dup_space),
            ]

    default_regulator = "gm"
    regulators = [default_regulator,
            default_regulator, default_regulator,
            "wm", default_regulator,
            "wm", "gw",
            "wb", default_regulator,
            "ww", default_regulator,
            ]

    width = .24
    for i, (xx, yy) in enumerate(locs):
        regulator = regulators[i]
        x1, x2 = xx - .5 * width, xx + .5 * width
        Glyph(root, x1, x2, yy)
        if i == 9:  # upper copy for non-functionalization
            continue

        # coding region
        x1, x2 = xx - .16 * width, xx + .45 * width
        Glyph(root, x1, x2, yy, fc="k")

        # two regulatory elements
        x1, x2 = xx - .4 * width, xx - .28 * width
        for xx, fc in zip((x1, x2), regulator):
            if fc == 'w':
                continue

            DoubleCircle(root, xx, yy, fc=fc)

        rotation = 30
        tip = .02
        if i == 0:
            ya = yy + tip
            root.text(x1, ya, _("Flower"), rotation=rotation, va="bottom")
            root.text(x2, ya, _("Root"), rotation=rotation, va="bottom")
        elif i == 7:
            ya = yy + tip
            root.text(x2, ya, _("Leaf"), rotation=rotation, va="bottom")

    # Draw arrows between panels (center)
    arrow_dist = .08
    ar_xpos = .5
    for ar_ypos in (.3, .53, .76):
        root.annotate(" ", (ar_xpos, ar_ypos),
                (ar_xpos, ar_ypos + arrow_dist),
                arrowprops=arrowprops)

    ar_ypos = .3
    for ar_xpos in (.2, .8):
        root.annotate(" ", (ar_xpos, ar_ypos),
                (.5, ar_ypos + arrow_dist),
                arrowprops=arrowprops)

    # Duplication, Degeneration
    xx = .6
    ys = (.76, .53)
    processes = ("Duplication", "Degeneration")
    for yy, process in zip(ys, processes):
        root.text(xx, yy + .02, process, fontweight="bold")

    # Label of fates
    xs = (.2, .5, .8)
    fates = ("Subfunctionalization", "Neofunctionalization",
            "Nonfunctionalization")
    yy = .05
    for xx, fate in zip(xs, fates):
        RoundLabel(root, xx, yy, fate)

    root.set_xlim(0, 1)
    root.set_ylim(0, 1)
    root.set_axis_off()

    figname = "demo.pdf"
    plt.savefig(figname, dpi=300)
    logging.debug("Figure saved to `{0}`".format(figname))


if __name__ == '__main__':
    main()
