"""Utilities for translating ORF detection"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import warnings

from collections import Counter
from collections import defaultdict

import pysam
from tqdm import *
import numpy as np
import pandas as pd

from .bam import split_bam
from .bam import count_rna_bam
from .constants import CUTOFF
from .fasta import FastaReader
from .gtf import GTFReader
from .infer_protocol import infer_protocol
from .metagene import metagene_coverage
from .metagene import align_metagenes
from .orf import ORF
from .plotting import plot_read_lengths
from .plotting import plot_metagene
from .prepare_orfs import prepare_orfs
from .statistics import coherence


def merge_read_lengths(alignments, psite_offsets):
    """
    Parameters
    ----------
    alignments: dict(dict(Counter))
                bam split by length, strand
    psite_offsets: dict
                   key is the length, value is the offset
    Returns
    -------
    merged_alignments: dict(dict)
                       alignments by merging all lengths
    """
    print('merging different lengths...')
    merged_alignments = defaultdict(Counter)

    for length, offset in psite_offsets.items():
        for strand in alignments[length]:
            for chrom, pos in alignments[length][strand]:
                count = alignments[length][strand][(chrom, pos)]
                if strand == '+':
                    pos_shifted = pos + offset
                else:
                    pos_shifted = pos - offset
                merged_alignments[strand][(chrom, pos_shifted)] += count
    return merged_alignments


def parse_annotation(annotation):
    """
    Parameters
    ----------
    annotation: string
          path of annotation file generated by prepare_orfs
    
    Returns
    -------
    cds: List[ORF]
         list of cds
    uorfs: List[ORF]
          list of candidate ORFs from 5'UTR
    dorfs: List[ORF]
          list of candidate ORFs from 3'UTR
    """

    cds = []
    uorfs = []
    dorfs = []
    print('parsing candidate ORFs...')
    with open(annotation, 'r') as anno:
        total_lines = len(['' for line in anno])
    with open(annotation, 'r') as anno:
        with tqdm(total=total_lines) as pbar:
            header = True
            for line in anno:
                pbar.update()
                if header:
                    header = False
                    continue
                orf = ORF.from_string(line)
                if orf is None:
                    continue
                if orf.category == 'CDS':
                    cds.append(orf)
                elif orf.category == 'uORF':
                    uorfs.append(orf)
                elif orf.category == 'dORF':
                    dorfs.append(orf)
    return (cds, uorfs, dorfs)


def orf_coverage(orf, alignments, offset_5p=20, offset_3p=0):
    """
    Parameters
    ----------
    orf: ORF
         instance of ORF
    alignments: dict(Counter)
                alignments summarized from bam by merging lengths
    offset_5p: int
               the number of nts to include from 5'prime
    offset_3p: int
               the number of nts to include from 3'prime

    Returns
    -------
    coverage: Series
              coverage for ORF for specific length
    """
    coverage = []
    chrom = orf.chrom
    strand = orf.strand
    if strand == '-':
        offset_5p, offset_3p = offset_3p, offset_5p
    first, last = orf.intervals[0], orf.intervals[-1]
    for pos in range(first.start - offset_5p, first.start):
        try:
            coverage.append(alignments[strand][(chrom, pos)])
        except KeyError:
            coverage.append(0)

    for iv in orf.intervals:
        for pos in range(iv.start, iv.end + 1):
            try:
                coverage.append(alignments[strand][(chrom, pos)])
            except KeyError:
                coverage.append(0)

    for pos in range(last.end + 1, last.end + offset_3p + 1):
        try:
            coverage.append(alignments[strand][(chrom, pos)])
        except KeyError:
            coverage.append(0)

    if strand == '-':
        coverage.reverse()
        return pd.Series(
            np.array(coverage),
            index=np.arange(-offset_3p,
                            len(coverage) - offset_3p))
    else:
        return pd.Series(
            np.array(coverage),
            index=np.arange(-offset_5p,
                            len(coverage) - offset_5p))


def export_orf_coverages(orfs, merged_alignments, prefix, testRNA=False):
    """
    Parameters
    ----------
    orfs: List[ORF]
          a list of candidate orfs
    merged_alignments: dict(dict)
                       alignments by merging all lengths
    prefix: str
            prefix for output file
    testRNA: bool
             if True, all coverages will be exported
    """
    print('exporting coverages for all ORFs...')
    to_write = 'ORF_ID\tcoverage\tcount\tlength\tnonzero\tperiodicity\tpval\n'
    for orf in tqdm(orfs):
        oid = orf.oid
        cov = orf_coverage(orf, merged_alignments)
        cov = cov.astype(int)
        cov = cov.tolist()
        count = sum(cov)
        length = len(cov)
        coh, pval, valid = coherence(cov)
        # if not testRNA and coh < CUTOFF:  # skip those fail the cutoff
        #     continue
        to_write += '{}\t{}\t{}\t{}\t{}\t{}\t{}\n'.format(
            oid, cov, count, length, valid, coh, pval)
    with open('{}_translating_ORFs.tsv'.format(prefix), 'w') as output:
        output.write(to_write)


def export_wig(merged_alignments, prefix):
    """
    Parameters
    ----------
    merged_alignments: dict(dict)
                       alignments by merging all lengths
    prefix: str
            prefix of output wig files
    """
    print('exporting merged alignments to wig file...')
    for strand in merged_alignments:
        to_write = ''
        cur_chrom = ''
        for chrom, pos in sorted(merged_alignments[strand]):
            if chrom != cur_chrom:
                cur_chrom = chrom
                to_write += 'variableStep chrom={}\n'.format(chrom)
            to_write += '{}\t{}\n'.format(
                pos, merged_alignments[strand][(chrom, pos)])
        if strand == '+':
            fname = '{}_pos.wig'.format(prefix)
        else:
            fname = '{}_neg.wig'.format(prefix)
        with open(fname, 'w') as output:
            output.write(to_write)


def detect_orfs(bam,
                prefix,
                gtf=None,
                fasta=None,
                annotation=None,
                protocol=None,
                testRNA=False):
    """
    Parameters
    ----------
    gtf: str
         Path to the GTF file
    fasta: str
           Path to the FASTA file
    bam: str
         Path to the bam file
    prefix: str
            prefix for all output files
    annotation: str
                Path for annontation files of candidate ORFs
                It will be automatically generated if None
    protocol: str
              'forward' for stranded, 'reverse' for reverse stranded
              It will be automatically inferred if None
    """

    cds = uorfs = dorfs = None
    if gtf and not isinstance(gtf, GTFReader):
        gtf = GTFReader(gtf)

    if fasta and not isinstance(fasta, FastaReader):
        fasta = FastaReader(fasta)

    if annotation is None:
        cds, uorfs, dorfs = prepare_orfs(gtf, fasta, prefix)
    else:
        cds, uorfs, dorfs = parse_annotation(annotation)

    if protocol is None:
        protocol = infer_protocol(bam, gtf, prefix)

    if testRNA:
        alignments = count_rna_bam(bam, protocol, prefix)
        export_orf_coverages(cds + uorfs + dorfs, alignments, prefix, True)
        return
    alignments, read_lengths = split_bam(bam, protocol, prefix)
    plot_read_lengths(read_lengths, prefix)
    metagenes = metagene_coverage(cds, alignments, read_lengths, prefix)
    plot_metagene(metagenes, read_lengths, prefix)
    psite_offsets = align_metagenes(metagenes, read_lengths, prefix)
    merged_alignments = merge_read_lengths(alignments, psite_offsets)
    export_wig(merged_alignments, prefix)
    export_orf_coverages(cds + uorfs + dorfs, merged_alignments, prefix)
