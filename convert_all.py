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

    return parser.parse_args()


proj_datumgrid = get_args().proj_datumgrid


class Obj(object):
    pass


with open(os.path.join(proj_datumgrid, 'filelist.csv')) as f:
    reader = csv.reader(f)
    first_line = True
    for row in reader:
        if first_line:
            assert row == ['filename', 'type', 'unit', 'source_crs', 'target_crs',
                           'interpolation_crs', 'agency_name', 'source', 'licence']
            first_line = False
            continue
        filename, type, unit, source_crs, target_crs, interpolation_crs, _, source, licence = row

        for subdir in ('.', 'europe', 'north-america', 'oceania', 'world'):
            candidate_filename = os.path.join(proj_datumgrid, subdir, filename)
            if os.path.exists(candidate_filename):
                filename = candidate_filename
                break

        #if os.path.basename(filename).startswith('HT2_'):
        #    pass
        #else:
        #    continue

        if type == 'HORIZONTAL_OFFSET':
            print('Processing ' + filename)
            args = Obj()
            args.source = filename
            args.dest = os.path.splitext(
                os.path.basename(filename))[0] + ".tif"
            args.do_not_write_error_samples = False
            args.accuracy_unit = None
            args.source_crs = source_crs
            args.target_crs = target_crs
            args.description = None
            args.copyright = "Derived from work by " + source + ". " + licence
            args.accuracy_unit = 'unknown' if os.path.basename(filename) in (
                'BWTA2017.gsb', 'DLx_ETRS89_geo.gsb', 'D73_ETRS89_geo.gsb') else None
            args.uint16_encoding = False
            args.positive_longitude_shift_value = 'east'
            args.datetime = datetime.date.today().strftime("%Y:%m:%d %H:%M:%S")

            tmpfilename = args.dest + '.tmp'
            gdal.Unlink(tmpfilename)
            ntv2_to_gtiff.create_unoptimized_file(
                args.source, tmpfilename, args)
            ntv2_to_gtiff.generate_optimized_file(tmpfilename, args.dest)
            ntv2_to_gtiff.check(args.source, args.dest, args)

            gdal.Unlink(tmpfilename)

        elif type == 'VERTICAL_OFFSET_GEOGRAPHIC_TO_VERTICAL':
            print('Processing ' + filename)
            args = Obj()
            args.source = filename
            args.dest = os.path.splitext(
                os.path.basename(filename))[0] + ".tif"
            args.source_crs = source_crs
            args.target_crs = target_crs
            args.description = None
            args.copyright = "Derived from work by " + source + ". " + licence
            args.datetime = datetime.date.today().strftime("%Y:%m:%d %H:%M:%S")
            args.type = 'GEOGRAPHIC_TO_VERTICAL'
            args.encoding = 'int32-scale-1-1000' if os.path.basename(filename).startswith(
                'CGG') or os.path.basename(filename).startswith('HT2_') else 'float32'
            args.ignore_nodata = None

            tmpfilename = args.dest + '.tmp'
            gdal.Unlink(tmpfilename)
            vertoffset_grid_to_gtiff.create_unoptimized_file(
                args.source, tmpfilename, args)
            vertoffset_grid_to_gtiff.generate_optimized_file(
                tmpfilename, args.dest)
            vertoffset_grid_to_gtiff.check(args.source, args.dest, args)

            gdal.Unlink(tmpfilename)

        elif type == 'VERTICAL_OFFSET_VERTICAL_TO_VERTICAL':
            print('Processing ' + filename)
            args = Obj()
            args.source = filename
            args.dest = os.path.splitext(
                os.path.basename(filename))[0] + ".tif"
            args.source_crs = source_crs
            args.target_crs = target_crs
            assert 'vertcon' in filename
            args.interpolation_crs = 'EPSG:4267'
            args.description = None
            args.copyright = "Derived from work by " + source + ". " + licence
            args.datetime = datetime.date.today().strftime("%Y:%m:%d %H:%M:%S")
            args.type = 'VERTICAL_TO_VERTICAL'
            args.encoding = 'float32'
            args.ignore_nodata = None

            tmpfilename = args.dest + '.tmp'
            gdal.Unlink(tmpfilename)
            vertoffset_grid_to_gtiff.create_unoptimized_file(
                args.source, tmpfilename, args)
            vertoffset_grid_to_gtiff.generate_optimized_file(
                tmpfilename, args.dest)
            vertoffset_grid_to_gtiff.check(args.source, args.dest, args)

            gdal.Unlink(tmpfilename)

        else:
            print('Skipping ' + filename)
