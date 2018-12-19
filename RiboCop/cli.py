"""Command line interface for RiboCop
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import numpy as np
import pandas as pd

import click
from click_help_colors import HelpColorsGroup
from . import __version__
from .detect_orfs import detect_orfs
from .infer_protocol import infer_protocol
from .prepare_orfs import prepare_orfs

click.disable_unicode_literals_warning = True
CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])


@click.group(
    cls=HelpColorsGroup,
    help_headers_color='yellow',
    help_options_color='green')
@click.version_option(version=__version__)
def cli():
    """RiboCop: Tool for detecting translating ORF from Ribo-seq data"""
    pass


###################### prepare-orfs function #########################################
@cli.command(
    'prepare-orfs',
    context_settings=CONTEXT_SETTINGS,
    help='Extract candidate ORFS based on GTF and FASTA files')
@click.option('--gtf', help='Path to GTF file', required=True)
@click.option('--fasta', help='Path to FASTA file', required=True)
@click.option('--prefix', help='Prefix to output file', required=True)
@click.option(
    '--min_orf_length',
    type=int,
    default=60,
    show_default=True,
    help='The minimum length (nts) of ORF to include')
@click.option(
    '--startcodon',
    default='ATG',
    show_default=True,
    help='Comma separated list of start codons')
@click.option(
    '--stopcodon',
    default='TAG,TAA,TGA',
    show_default=True,
    help='Comma separated list of stop codons')
def prepare_orfs_cmd(gtf, fasta, prefix, min_orf_length, startcodon,
                     stopcodon):
    prepare_orfs(gtf, fasta, prefix, min_orf_length, startcodon, stopcodon)


###################### detect-orfs function #########################################
@cli.command(
    'detect-orfs',
    context_settings=CONTEXT_SETTINGS,
    help='Detect translating ORFs from BAM file')
@click.option('--bam', help='Path to BAM file', required=True)
@click.option(
    '--annotation',
    help=('Path to annotation file\n'
          'This file should be generated using prepare-orfs'),
    required=True)
@click.option('--gtf', help='Path to GTF file', required=True)
@click.option('--prefix', help='Prefix to output file', required=True)
@click.option(
    '--readlength',
    default=None,
    show_default=True,
    help=('Comma separated read lengths to be used, such as 28,29,30\n'
          'If not provided, the metagene level '
          'periodic read lengths will be used'))
@click.option(
    '--offset',
    default=None,
    show_default=True,
    help=('Comma separated P-site offsets for each read length '
          'matching the read lengths provided.\n'
          'If not provided, reads from different read lengths will be '
          'automatically aligned using cross-correlation'))
@click.option(
    '--outputall',
    help=('Whether output all ORFs including those '
          'non-translating ones'),
    is_flag=True)
def detect_orfs_cmd(bam, annotation, gtf, prefix, readlength, offset,
                    outputall):
    detect_orfs(bam, prefix, gtf=gtf, annotation=annotation)


###################### infer-protocol function #########################################
@cli.command(
    'infer-protocol',
    context_settings=CONTEXT_SETTINGS,
    help='Infer protocol from BAM')
@click.option('--bam', help='Path to bam file', required=True)
@click.option('--gtf', help='Path to GTF file', required=True)
@click.option('--prefix', help='Prefix to output file')
@click.option(
    '--n_reads',
    type=int,
    default=20000,
    help='Number of mapped reads to use for estimation')
def infer_protocol_cmd(bam, gtf, prefix, n_reads):
    infer_protocol(bam, gtf, prefix, n_reads)
