"""
Wrapper for calling Bio.Entrez tools to get the sequence from a list of IDs
"""

import os
import os.path as op
import sys
import time
import logging
import urllib2

from optparse import OptionParser
from Bio import Entrez, SeqIO

from jcvi.formats.base import must_open
from jcvi.formats.fasta import print_first_difference
from jcvi.utils.iter import grouper
from jcvi.apps.console import green
from jcvi.apps.base import ActionDispatcher, mkdir, debug
debug()

myEmail = "htang@jcvi.org"
Entrez.email = myEmail


def batch_taxonomy(list_of_taxids):
    """
    Retrieve list of taxids, and generate latin names
    """
    for taxid in list_of_taxids:
        handle = Entrez.efetch(db='Taxonomy', id=taxid, retmode="xml")
        records = Entrez.read(handle)
        yield records[0]["ScientificName"]


def batch_entrez(list_of_terms, db="nuccore", retmax=1, rettype="fasta",
            batchsize=1):
    """
    Retrieve multiple rather than a single record
    """

    for term in list_of_terms:

        logging.debug("Search term %s" % term)
        success = False
        ids = None
        if not term:
            continue

        while not success:
            try:
                search_handle = Entrez.esearch(db=db, retmax=retmax, term=term)
                rec = Entrez.read(search_handle)
                success = True
                ids = rec["IdList"]
            except (urllib2.HTTPError, urllib2.URLError,
                    RuntimeError, KeyError) as e:
                logging.error(e)
                logging.debug("wait 5 seconds to reconnect...")
                time.sleep(5)

        if not ids:
            logging.error("term {0} not found".format(term))
            continue

        assert ids
        nids = len(ids)
        if nids > 1:
            logging.debug("A total of {0} results found.".format(nids))

        if batchsize != 1:
            logging.debug("Use a batch size of {0}.".format(batchsize))

        ids = list(grouper(batchsize, ids))

        for id in ids:
            id = [x for x in id if x]
            size = len(id)
            id = ",".join(id)

            success = False
            while not success:
                try:
                    fetch_handle = Entrez.efetch(db=db, id=id, rettype=rettype,
                            email=myEmail)
                    success = True
                except (urllib2.HTTPError, urllib2.URLError,
                        RuntimeError) as e:
                    logging.error(e)
                    logging.debug("wait 5 seconds to reconnect...")
                    time.sleep(5)

            yield id, size, term, fetch_handle


def main():

    actions = (
        ('fetch', 'fetch records from a list of GenBank accessions'),
        ('bisect', 'determine the version of the accession'),
        )
    p = ActionDispatcher(actions)
    p.dispatch(globals())


def get_first_rec(fastafile):
    """
    Returns the first record in the fastafile
    """
    f = list(SeqIO.parse(fastafile, "fasta"))

    if len(f) > 1:
        logging.debug("{0} records found in {1}, using the first one".\
                format(len(f), fastafile))

    return f[0]


def bisect(args):
    """
    %prog bisect acc accession.fasta

    determine the version of the accession, based on a fasta file.
    This proceeds by a sequential search from xxxx.1 to the latest record.
    """
    p = OptionParser(bisect.__doc__)

    opts, args = p.parse_args(args)

    if len(args) != 2:
        sys.exit(p.print_help())

    acc, fastafile = args
    arec = get_first_rec(fastafile)

    valid = None
    for i in range(1, 100):
        term = "%s.%d" % (acc, i)
        try:
            query = list(batch_entrez([term]))
        except AssertionError as e:
            logging.debug("no records found for %s. terminating." % term)
            return

        id, term, handle = query[0]
        brec = SeqIO.parse(handle, "fasta").next()

        match = print_first_difference(arec, brec, ignore_case=True,
                ignore_N=True, rc=True)
        if match:
            valid = term
            break

    if valid:
        print
        print green("%s matches the sequence in `%s`" % (valid, fastafile))


def fetch(args):
    """
    %prog fetch <filename|term>

    `filename` contains a list of terms to search. Or just one term. If the
    results are small in size, e.g. "--format=acc", use "--batchsize=100" to speed
    the download.
    """
    p = OptionParser(fetch.__doc__)

    allowed_databases = {"fasta": ["genome", "nuccore", "nucgss", "protein", "nucest"],
                         "asn.1": ["genome", "nuccore", "nucgss", "protein"],
                         "gb"   : ["genome", "nuccore", "nucgss"],
                         "est"  : ["nucest"],
                         "gss"  : ["nucgss"],
                         "acc"  : ["nuccore"],
                        }

    valid_formats = tuple(allowed_databases.keys())
    valid_databases = ("genome", "nuccore", "nucest", "nucgss", "protein")

    p.add_option("--noversion", dest="noversion",
            default=False, action="store_true",
            help="Remove trailing accession versions")
    p.add_option("--format", default="fasta", choices=valid_formats,
            help="download format [default: %default]")
    p.add_option("--database", default="nuccore", choices=valid_databases,
            help="search database [default: %default]")
    p.add_option("--outdir", default=None,
            help="output directory, with accession number as filename")
    p.add_option("--retmax", default=10000, type="int",
            help="how many results to return [default: %default]")
    p.add_option("--skipcheck", default=False, action="store_true",
            help="turn off prompt to check file existence [default: %default]")
    p.add_option("--batchsize", default=500, type="int",
            help="download the results in batch for speed-up [default: %default]")
    opts, args = p.parse_args(args)

    if len(args) != 1:
        sys.exit(p.print_help())

    filename, = args
    if op.exists(filename):
        pf = filename.rsplit(".", 1)[0]
        list_of_terms = [row.strip() for row in open(filename)]
        if opts.noversion:
            list_of_terms = [x.rsplit(".", 1)[0] for x in list_of_terms]
    else:
        pf = filename
        # the filename is the search term
        list_of_terms = [filename.strip()]

    fmt = opts.format
    database = opts.database
    batchsize = opts.batchsize

    assert database in allowed_databases[fmt], \
        "For output format '{0}', allowed databases are: {1}".\
        format(fmt, allowed_databases[fmt])
    assert batchsize >= 1, "batchsize must >= 1"

    if " " in pf:
        pf = "out"

    outfile = "{0}.{1}".format(pf, fmt)

    outdir = opts.outdir
    if outdir:
        mkdir(outdir)

    # If noprompt, will not check file existence
    if not outdir:
        fw = must_open(outfile, "w", checkexists=True, \
                skipcheck=opts.skipcheck)
        if fw is None:
            return

    seen = set()
    totalsize = 0
    for id, size, term, handle in batch_entrez(list_of_terms, retmax=opts.retmax, \
                                 rettype=fmt, db=database, batchsize=batchsize):
        if outdir:
            outfile = op.join(outdir, "{0}.{1}".format(term, fmt))
            fw = must_open(outfile, "w", checkexists=True, \
                    skipcheck=opts.skipcheck)
            if fw is None:
                continue

        rec = handle.read()
        if id in seen:
            logging.error("Duplicate key ({0}) found".format(rec))
            continue

        totalsize += size
        print >> fw, rec
        print >> fw

        seen.add(id)

    if seen:
        print >> sys.stderr, "A total of {0} {1} records downloaded.".\
                format(totalsize, fmt.upper())

    return outfile


if __name__ == '__main__':
    main()
