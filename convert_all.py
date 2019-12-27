#!/usr/bin/env python
###############################################################################
# $Id$
#
#  Project:  PROJ
#  Purpose:  Convert proj-datumgrid to GeoTIFF
#  Author:   Even Rouault <even.rouault at spatialys.com>
#
###############################################################################
#  Copyright (c) 2019, Even Rouault <even.rouault at spatialys.com>
#
#  Permission is hereby granted, free of charge, to any person obtaining a
#  copy of this software and associated documentation files (the "Software"),
#  to deal in the Software without restriction, including without limitation
#  the rights to use, copy, modify, merge, publish, distribute, sublicense,
#  and/or sell copies of the Software, and to permit persons to whom the
#  Software is furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included
#  in all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
#  OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
#  THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#  DEALINGS IN THE SOFTWARE.
###############################################################################

from osgeo import gdal
import argparse
import csv
import datetime
import os
import ntv2_to_gtiff
import vertoffset_grid_to_gtiff


def get_args():
    parser = argparse.ArgumentParser(
        description='Convert proj-datumgrid to GeoTIFF.')
    parser.add_argument('proj_datumgrid',
                        help='proj-datumgrid directory')
    parser.add_argument('target_dir',
                        help='target directory')

    parser.add_argument('--overwrite',
                        action='store_true', default=False,
                        help='Overwrite grids already existing in target dir')

    parser.add_argument('--only',
                        help='Convert only mentionned grid')

    return parser.parse_args()


args = get_args()
proj_datumgrid = args.proj_datumgrid
target_dir = args.target_dir

if not os.path.exists(target_dir):
    os.mkdir(target_dir)

class Obj(object):
    pass


with open(os.path.join(proj_datumgrid, 'filelist.csv')) as f:
    reader = csv.reader(f)
    first_line = True
    for row in reader:
        if first_line:
            assert row == ['filename', 'type', 'area', 'unit', 'source_crs', 'target_crs',
                           'interpolation_crs', 'agency_name', 'source', 'licence']
            first_line = False
            continue
        src_filename, type, area, unit, source_crs, target_crs, interpolation_crs, agency_name, source, licence = row

        filename = None
        for subdir in ('.', 'europe', 'north-america', 'oceania', 'world'):
            candidate_filename = os.path.join(proj_datumgrid, subdir, src_filename)
            if os.path.exists(candidate_filename):
                filename = candidate_filename
                break

        if not filename:
            print('Cannot find ' + src_filename)
            continue

        this_file_target_dir = os.path.join(target_dir, agency_name)
        if not os.path.exists(this_file_target_dir):
            os.mkdir(this_file_target_dir)

        if args.only:
            if os.path.basename(filename) == args.only:
                pass
            else:
                continue

        cvt_args = Obj()
        cvt_args.source = filename
        cvt_args.dest = os.path.join(this_file_target_dir,os.path.splitext(
            os.path.basename(filename))[0] + ".tif")

        if os.path.exists(cvt_args.dest) and not args.overwrite:
            print('Skipping ' + cvt_args.source)
            continue

        if type == 'HORIZONTAL_OFFSET':
            print('Processing ' + filename)
            cvt_args.do_not_write_error_samples = False
            cvt_args.accuracy_unit = None
            cvt_args.source_crs = source_crs
            cvt_args.target_crs = target_crs
            cvt_args.description = None
            cvt_args.copyright = "Derived from work by " + source + ". " + licence
            cvt_args.accuracy_unit = 'unknown' if os.path.basename(filename) in (
                'BWTA2017.gsb', 'DLx_ETRS89_geo.gsb', 'D73_ETRS89_geo.gsb') else None
            cvt_args.uint16_encoding = False
            cvt_args.positive_longitude_shift_value = 'east'
            cvt_args.datetime = datetime.date.today().strftime("%Y:%m:%d %H:%M:%S")
            cvt_args.area_of_use = area

            tmpfilename = cvt_args.dest + '.tmp'
            gdal.Unlink(tmpfilename)
            ntv2_to_gtiff.create_unoptimized_file(
                cvt_args.source, tmpfilename, cvt_args)
            ntv2_to_gtiff.generate_optimized_file(tmpfilename, cvt_args.dest)
            ntv2_to_gtiff.check(cvt_args.source, cvt_args.dest, cvt_args)

            gdal.Unlink(tmpfilename)

        elif type == 'VERTICAL_OFFSET_GEOGRAPHIC_TO_VERTICAL':
            print('Processing ' + filename)
            cvt_args.source_crs = source_crs
            cvt_args.target_crs = target_crs
            cvt_args.description = None
            cvt_args.copyright = "Derived from work by " + source + ". " + licence
            cvt_args.datetime = datetime.date.today().strftime("%Y:%m:%d %H:%M:%S")
            cvt_args.type = 'GEOGRAPHIC_TO_VERTICAL'
            cvt_args.encoding = 'int32-scale-1-1000' if os.path.basename(filename).startswith(
                'CGG') or os.path.basename(filename).startswith('HT2_') else 'float32'
            cvt_args.ignore_nodata = None
            cvt_args.area_of_use = area

            tmpfilename = cvt_args.dest + '.tmp'
            gdal.Unlink(tmpfilename)
            vertoffset_grid_to_gtiff.create_unoptimized_file(
                cvt_args.source, tmpfilename, cvt_args)
            vertoffset_grid_to_gtiff.generate_optimized_file(
                tmpfilename, cvt_args.dest)
            vertoffset_grid_to_gtiff.check(cvt_args.source, cvt_args.dest, cvt_args)

            gdal.Unlink(tmpfilename)

        elif type == 'VERTICAL_OFFSET_VERTICAL_TO_VERTICAL':
            print('Processing ' + filename)
            cvt_args.source_crs = source_crs
            cvt_args.target_crs = target_crs
            assert 'vertcon' in filename or '-nzvd2016.gtx' in filename
            cvt_args.interpolation_crs = 'EPSG:4267'
            cvt_args.description = None
            cvt_args.copyright = "Derived from work by " + source + ". " + licence
            cvt_args.datetime = datetime.date.today().strftime("%Y:%m:%d %H:%M:%S")
            cvt_args.type = 'VERTICAL_TO_VERTICAL'
            cvt_args.encoding = 'float32'
            cvt_args.ignore_nodata = None
            cvt_args.area_of_use = area

            tmpfilename = cvt_args.dest + '.tmp'
            gdal.Unlink(tmpfilename)
            vertoffset_grid_to_gtiff.create_unoptimized_file(
                cvt_args.source, tmpfilename, cvt_args)
            vertoffset_grid_to_gtiff.generate_optimized_file(
                tmpfilename, cvt_args.dest)
            vertoffset_grid_to_gtiff.check(cvt_args.source, cvt_args.dest, cvt_args)

            gdal.Unlink(tmpfilename)

        else:
            print('Skipping ' + filename)
