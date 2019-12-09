#!/usr/bin/env python
###############################################################################
# $Id$
#
#  Project:  PROJ
#  Purpose:  Convert a NTv2 file into an optimized GTiff
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

# python ./ntv2_to_gtiff.py --copyright "Derived from work by IGN France. Open License https://www.etalab.gouv.fr/wp-content/uploads/2014/05/Open_Licence.pdf" --source-crs EPSG:4275 --target-crs EPSG:4171 /home/even/proj/proj-datumgrid/ntf_r93.gsb ntf_r93.tif
# python ./ntv2_to_gtiff.py --copyright "Derived from work by LGL-BW.DE. Data licence Germany - attribution - version 2.0: https://www.govdata.de/dl-de/by-2-0"  --source-crs EPSG:4314 --target-crs EPSG:4258 /home/even/proj/proj-datumgrid/europe/BWTA2017.gsb BWTA2017.tif --do-not-write-error-samples
# python ./ntv2_to_gtiff.py --copyright "Derived from work by Natural Resources Canada. Open Government Licence - Canada: http://open.canada.ca/en/open-government-licence-canada" --source-crs EPSG:4267 --target-crs EPSG:4269 /home/even/proj/proj-datumgrid/north-america/ntv2_0.gsb ntv2_0.tif
# python ./ntv2_to_gtiff.py --copyright "Derived from work by ICSM. Creative Commons Attribution 4.0: https://creativecommons.org/licenses/by/4.0/" --source-crs EPSG:4283  --target-crs EPSG:7844 /home/even/proj/proj-datumgrid/oceania/GDA94_GDA2020_conformal.gsb GDA94_GDA2020_conformal.tif


from osgeo import gdal
from osgeo import osr
import argparse
import datetime
import os
import struct


def get_args():
    parser = argparse.ArgumentParser(
        description='Convert NTv2 grid into PROJ GeoTIFF.')
    parser.add_argument('source',
                        help='Source NTv2 file')
    parser.add_argument('dest',
                        help='Destination GeoTIFF file')

    parser.add_argument('--source-crs', dest='source_crs', required=True,
                        help='Source CRS as EPSG:XXXX or WKT')

    parser.add_argument('--target-crs', dest='target_crs', required=True,
                        help='Target CRS as EPSG:XXXX or WKT')

    parser.add_argument('--copyright', dest='copyright', required=True,
                        help='Copyright info')

    parser.add_argument('--description', dest='description',
                        help='Description')

    parser.add_argument('--do-not-write-error-samples', dest='do_not_write_error_samples',
                        action='store_true')

    parser.add_argument('--uint16-encoding', dest='uint16_encoding',
                        action='store_true',
                        help='Use uint16 storage with linear scaling/offseting')

    parser.add_argument('--datetime', dest='datetime',
                        help='Value for TIFF DateTime tag as YYYY:MM:DD HH:MM:SS, or "NONE" to not write it. If not specified, current date time is used')

    return parser.parse_args()


def get_year_month_day(src_date, src_basename):
    assert len(src_date) == 8
    if (src_date[2] == '-' and src_date[5] == '-') or \
            (src_date[2] == '/' and src_date[5] == '/'):
        if src_basename.startswith('rdtrans') or \
                src_basename.startswith('ntf_r93') or \
                src_basename.startswith('BWTA2017') or \
                src_basename.startswith('BETA2007') or \
                src_basename.startswith('D73_ETRS89_geo') or \
                src_basename.startswith('DLx_ETRS89_geo'):
            # rdtrans2018.gsb has 22-11-18 &
            # ntf_r93.gsb has 31/10/07, hence D-M-Y
            day = int(src_date[0:2])
            month = int(src_date[3:5])
            year = int(src_date[6:8])
        else:
            # CHENyx06a.gsb has 09-07-22 & ntv2_0.gsb and
            # (other NRCan datasets) has 95-06-30, hence Y-M-D
            year = int(src_date[0:2])
            month = int(src_date[3:5])
            day = int(src_date[6:8])
        if year >= 90:
            year += 1900
        else:
            assert year <= 50
            year += 2000
    else:
        if src_basename in ('nzgd2kgrid0005.gsb',
                            'A66_National_13_09_01.gsb',
                            'National_84_02_07_01.gsb',
                            'AT_GIS_GRID.gsb') or \
                src_basename.startswith('GDA94_GDA2020'):
            # nzgd2kgrid0005 has 20111999, hence D-M-Y
            day = int(src_date[0:2])
            month = int(src_date[2:4])
            year = int(src_date[4:8])
        elif src_basename == 'bd72lb72_etrs89lb08.gsb':
            # bd72lb72_etrs89lb08 has 20142308, hence Y-D-M
            year = int(src_date[0:4])
            day = int(src_date[4:6])
            month = int(src_date[6:8])
        else:
            year = int(src_date[0:4])
            month = int(src_date[4:6])
            day = int(src_date[6:8])
    return year, month, day


def create_unoptimized_file(sourcefilename, tmpfilename, args):
    src_ds = gdal.Open(sourcefilename)
    assert src_ds.GetDriver().ShortName == 'NTv2'
    subdatsets = [(sourcefilename, None)]
    subdatsets += src_ds.GetSubDatasets()

    # Build a subgrids dict whose key is a parent grid name and the
    # value the list of subgrids
    subgrids = {}
    for subds in subdatsets:
        src_ds = gdal.Open(subds[0])
        parent_name = src_ds.GetMetadataItem('PARENT')
        if parent_name == 'NONE':
            continue
        grid_name = src_ds.GetMetadataItem('SUB_NAME')
        if parent_name in subgrids:
            subgrids[parent_name].append(grid_name)
        else:
            subgrids[parent_name] = [grid_name]

    nbands = 2 if args.do_not_write_error_samples else 4

    compact_md = True if len(subdatsets) > 50 else False

    for idx_ifd, subds in enumerate(subdatsets):
        src_ds = gdal.Open(subds[0])
        assert src_ds.GetMetadataItem('GS_TYPE') == 'SECONDS'

        tmp_ds = gdal.GetDriverByName('GTiff').Create('/vsimem/tmp',
                                                      src_ds.RasterXSize,
                                                      src_ds.RasterYSize,
                                                      nbands,
                                                      gdal.GDT_Float32 if not args.uint16_encoding else gdal.GDT_UInt16)
        src_crs = osr.SpatialReference()
        src_crs.SetFromUserInput(args.source_crs)
        tmp_ds.SetSpatialRef(src_crs)
        tmp_ds.SetGeoTransform(src_ds.GetGeoTransform())
        tmp_ds.SetMetadataItem('AREA_OR_POINT', 'Point')
        tmp_ds.SetMetadataItem('TYPE', 'HORIZONTAL_OFFSET')

        grid_name = src_ds.GetMetadataItem('SUB_NAME')
        tmp_ds.SetMetadataItem('grid_name', grid_name)
        parent_name = src_ds.GetMetadataItem('PARENT')
        if parent_name != 'NONE':
            tmp_ds.SetMetadataItem('parent_name', parent_name)
        if grid_name in subgrids:
            tmp_ds.SetMetadataItem(
                'number_of_nested_grids', str(len(subgrids[grid_name])))

        if args.uint16_encoding:
            for i in (1, 2):
                min, max = src_ds.GetRasterBand(i).ComputeRasterMinMax()
                data = src_ds.GetRasterBand(i).ReadAsArray()
                scale = (max - min) / 65535
                data = (data - min) / scale
                tmp_ds.GetRasterBand(i).WriteArray(data)
                tmp_ds.GetRasterBand(i).SetOffset(min)
                tmp_ds.GetRasterBand(i).SetScale(scale)
                if idx_ifd == 0 or not compact_md:
                    tmp_ds.GetRasterBand(i).SetDescription(
                        'latitude_offset' if i == 1 else 'longitude_offset')
                    tmp_ds.GetRasterBand(i).SetUnitType('arc-second')

            if nbands == 4:
                for i in (3, 4):
                    min, max = src_ds.GetRasterBand(i).ComputeRasterMinMax()
                    data = src_ds.GetRasterBand(i).ReadAsArray()
                    scale = (max - min) / 65535
                    if scale == 0:
                        data = 0 * data
                    else:
                        data = (data - min) / scale
                    tmp_ds.GetRasterBand(i).WriteArray(data)
                    tmp_ds.GetRasterBand(i).SetOffset(min)
                    tmp_ds.GetRasterBand(i).SetScale(scale)
                    if idx_ifd == 0 or not compact_md:
                        tmp_ds.GetRasterBand(i).SetDescription(
                            'latitude_offset_accuracy' if i == 3 else 'longitude_offset_accuracy')
                        tmp_ds.GetRasterBand(i).SetUnitType('metre')

        else:
            for i in (1, 2):
                data = src_ds.GetRasterBand(i).ReadRaster()
                tmp_ds.GetRasterBand(i).WriteRaster(0, 0, src_ds.RasterXSize, src_ds.RasterYSize,
                                                    data)
                if idx_ifd == 0 or not compact_md:
                    tmp_ds.GetRasterBand(i).SetDescription(
                        'latitude_offset' if i == 1 else 'longitude_offset')
                    tmp_ds.GetRasterBand(i).SetUnitType('arc-second')

            if nbands == 4:
                for i in (3, 4):
                    data = src_ds.GetRasterBand(i).ReadRaster()
                    tmp_ds.GetRasterBand(i).WriteRaster(0, 0, src_ds.RasterXSize, src_ds.RasterYSize,
                                                        data)
                    if idx_ifd == 0 or not compact_md:
                        tmp_ds.GetRasterBand(i).SetDescription(
                            'latitude_offset_accuracy' if i == 3 else 'longitude_offset_accuracy')
                        tmp_ds.GetRasterBand(i).SetUnitType('metre')

        dst_crs = osr.SpatialReference()
        dst_crs.SetFromUserInput(args.target_crs)
        dst_auth_name = dst_crs.GetAuthorityName(None)
        dst_auth_code = dst_crs.GetAuthorityCode(None)
        if idx_ifd == 0 or not compact_md:
            if dst_auth_name == 'EPSG' and dst_auth_code:
                tmp_ds.SetMetadataItem('target_crs_epsg_code', dst_auth_code)
            else:
                tmp_ds.SetMetadataItem(
                    'target_crs_wkt', dst_crs.ExportToWkt(['FORMAT=WKT2_2018']))

        if idx_ifd == 0:
            desc = args.description
            if not desc:
                src_auth_name = src_crs.GetAuthorityName(None)
                src_auth_code = src_crs.GetAuthorityCode(None)

                desc = src_crs.GetName()
                if src_auth_name and src_auth_code:
                    desc += ' (' + src_auth_name + ':' + src_auth_code + ')'
                desc += ' to '
                desc += dst_crs.GetName()
                if dst_auth_name and dst_auth_code:
                    desc += ' (' + dst_auth_name + ':' + dst_auth_code + ')'
                desc += '. Converted from '
                src_basename = os.path.basename(args.source)
                desc += src_basename

                version = src_ds.GetMetadataItem('VERSION').strip()
                extra_info = []
                if version not in ('NTv2.0',):
                    extra_info.append('version ' + version)

                src_date = src_ds.GetMetadataItem('UPDATED').strip()
                created_date = None
                if not src_date:
                    src_date = src_ds.GetMetadataItem('CREATED').strip()
                    if src_date:
                        created_date = src_date
                if src_date:
                    year, month, day = get_year_month_day(
                        src_date, src_basename)

                    # Various sanity checks
                    assert day >= 1 and day <= 31
                    assert month >= 1 and month <= 12
                    assert year >= 1980
                    assert year <= datetime.datetime.now().year
                    # assume agencies only work monday to friday...
                    # except in Belgium where they work on sundays
                    # and in NZ on saturdays
                    if src_basename not in ('nzgd2kgrid0005.gsb', 'bd72lb72_etrs89lb08.gsb'):
                        assert datetime.datetime(
                            year, month, day).weekday() <= 4

                    # Sanity check that creation_date <= last_updated_date
                    if created_date:
                        year_created, month_created, day_created = get_year_month_day(
                            created_date, src_basename)
                        assert year_created * 10000 + month_created * 100 + \
                            day_created <= year * 10000 + month * 100 + day

                    extra_info.append(
                        'last updated on %04d-%02d-%02d' % (year, month, day))

            if extra_info:
                desc += ' (' + ', '.join(extra_info) + ')'

            tmp_ds.SetMetadataItem('TIFFTAG_IMAGEDESCRIPTION', desc)
            if args.copyright:
                tmp_ds.SetMetadataItem('TIFFTAG_COPYRIGHT', args.copyright)
            if args.datetime and args.datetime != 'NONE':
                tmp_ds.SetMetadataItem('TIFFTAG_DATETIME', args.datetime)

        options = ['PHOTOMETRIC=MINISBLACK',
                   'COMPRESS=DEFLATE',
                   'PREDICTOR=3' if not args.uint16_encoding else 'PREDICTOR=2',
                   'INTERLEAVE=BAND',
                   'GEOTIFF_VERSION=1.1']
        if tmp_ds.RasterXSize > 256 and tmp_ds.RasterYSize > 256:
            options.append('TILED=YES')
        else:
            options.append('BLOCKYSIZE=' + str(tmp_ds.RasterYSize))
        if gdal.VSIStatL(tmpfilename) is not None:
            options.append('APPEND_SUBDATASET=YES')

        assert gdal.GetDriverByName('GTiff').CreateCopy(tmpfilename, tmp_ds,
                                                        options=options)


def generate_optimized_file(tmpfilename, destfilename, args):

    TIFF_BYTE = 1        # 8-bit unsigned integer
    TIFF_ASCII = 2       # 8-bit bytes w/ last byte null
    TIFF_SHORT = 3       # 16-bit unsigned integer
    TIFF_LONG = 4        # 32-bit unsigned integer
    TIFF_RATIONAL = 5    # 64-bit unsigned fraction
    TIFF_SBYTE = 6       # !8-bit signed integer
    TIFF_UNDEFINED = 7   # !8-bit untyped data
    TIFF_SSHORT = 8      # !16-bit signed integer
    TIFF_SLONG = 9       # !32-bit signed integer
    TIFF_SRATIONAL = 10  # !64-bit signed fraction
    TIFF_FLOAT = 11      # !32-bit IEEE floating point
    TIFF_DOUBLE = 12     # !64-bit IEEE floating point
    TIFF_IFD = 13        # %32-bit unsigned integer (offset)
    TIFF_LONG8 = 16      # BigTIFF 64-bit unsigned integer
    TIFF_SLONG8 = 17     # BigTIFF 64-bit signed integer
    TIFF_IFD8 = 18        # BigTIFF 64-bit unsigned integer (offset)

    TIFFTAG_STRIPOFFSETS = 273
    TIFFTAG_STRIPBYTECOUNTS = 279
    TIFFTAG_TILEOFFSETS = 324
    TIFFTAG_TILEBYTECOUNTS = 325

    TIFFTAG_GDAL_METADATA = 42112

    typesize = {}
    typesize[TIFF_BYTE] = 1
    typesize[TIFF_ASCII] = 1
    typesize[TIFF_SHORT] = 2
    typesize[TIFF_LONG] = 4
    typesize[TIFF_RATIONAL] = 8
    typesize[TIFF_SBYTE] = 1
    typesize[TIFF_UNDEFINED] = 1
    typesize[TIFF_SSHORT] = 2
    typesize[TIFF_SLONG] = 4
    typesize[TIFF_SRATIONAL] = 8
    typesize[TIFF_FLOAT] = 4
    typesize[TIFF_DOUBLE] = 8
    typesize[TIFF_IFD] = 4
    typesize[TIFF_LONG8] = 8
    typesize[TIFF_SLONG8] = 8
    typesize[TIFF_IFD8] = 8

    class OfflineTag:
        def __init__(self, tagtype, nvalues, data, fileoffset_in_out_ifd):
            self.tagtype = tagtype
            self.nvalues = nvalues
            self.data = data
            self.fileoffset_in_out_ifd = fileoffset_in_out_ifd

        def unpack_array(self):
            if self.tagtype == TIFF_SHORT:
                return struct.unpack('<' + ('H' * self.nvalues), self.data)
            elif self.tagtype == TIFF_LONG:
                return struct.unpack('<' + ('I' * self.nvalues), self.data)
            else:
                assert False

    class IFD:
        def __init__(self, tagdict):
            self.tagdict = tagdict

    in_f = open(tmpfilename, 'rb')
    signature = in_f.read(4)
    assert signature == b'\x49\x49\x2A\x00'
    next_ifd_offset = struct.unpack('<I', in_f.read(4))[0]

    out_f = open(destfilename, 'wb')
    out_f.write(signature)
    next_ifd_offset_out_offset = 4
    # placeholder for pointer to next IFD
    out_f.write(struct.pack('<I', 0xDEADBEEF))

    out_f.write(b'\n-- Generated by ntv2_to_gtiff.py v1.0 --\n')
    essential_metadata_size_hint_offset_to_patch = out_f.tell()
    dummy_metadata_hint = b'-- Metadata size: XXXXXX --\n'
    out_f.write(dummy_metadata_hint)

    ifds = []

    offlinedata_to_offset = {}

    reuse_offlinedata = True

    while next_ifd_offset != 0:

        in_f.seek(next_ifd_offset)

        cur_pos = out_f.tell()
        if (cur_pos % 2) == 1:
            out_f.write(b'\x00')
            cur_pos += 1
        out_f.seek(next_ifd_offset_out_offset)
        out_f.write(struct.pack('<I', cur_pos))
        out_f.seek(cur_pos)

        numtags = struct.unpack('<H', in_f.read(2))[0]
        out_f.write(struct.pack('<H', numtags))

        tagdict = {}

        # Write IFD
        for i in range(numtags):
            tagid = struct.unpack('<H', in_f.read(2))[0]
            tagtype = struct.unpack('<H', in_f.read(2))[0]
            tagnvalues = struct.unpack('<I', in_f.read(4))[0]
            tagvalueoroffset = struct.unpack('<I', in_f.read(4))[0]
            #print(tagid, tagtype, tagnvalues, tagvalueoroffset)
            tagvalsize = typesize[tagtype] * tagnvalues

            out_f.write(struct.pack('<H', tagid))
            out_f.write(struct.pack('<H', tagtype))
            out_f.write(struct.pack('<I', tagnvalues))
            if tagvalsize <= 4:
                out_f.write(struct.pack('<I', tagvalueoroffset))
            else:
                curinoff = in_f.tell()
                in_f.seek(tagvalueoroffset)
                tagdata = in_f.read(tagvalsize)
                in_f.seek(curinoff)

                if reuse_offlinedata and tagdata in offlinedata_to_offset:
                    out_f.write(struct.pack(
                        '<I', offlinedata_to_offset[tagdata]))
                else:
                    tagdict[tagid] = OfflineTag(
                        tagtype, tagnvalues, tagdata, out_f.tell())
                    out_f.write(struct.pack('<I', 0xDEADBEEF))  # placeholder

        next_ifd_offset = struct.unpack('<I', in_f.read(4))[0]
        next_ifd_offset_out_offset = out_f.tell()
        # placeholder for pointer to next IFD
        out_f.write(struct.pack('<I', 0xDEADBEEF))

        # Write data for all out-of-line tags,
        # except the offset and byte count ones, and the GDAL metadata for the
        # IFDs after the first one, and patch IFD entries
        for id in tagdict:
            if id in (TIFFTAG_STRIPOFFSETS, TIFFTAG_STRIPBYTECOUNTS,
                      TIFFTAG_TILEOFFSETS, TIFFTAG_TILEBYTECOUNTS):
                continue
            if id == TIFFTAG_GDAL_METADATA:
                if len(ifds) != 0:
                    continue
            cur_pos = out_f.tell()
            out_f.seek(tagdict[id].fileoffset_in_out_ifd)
            out_f.write(struct.pack('<I', cur_pos))
            out_f.seek(cur_pos)
            out_f.write(tagdict[id].data)
            if reuse_offlinedata:
                offlinedata_to_offset[tagdict[id].data] = cur_pos

        ifds.append(IFD(tagdict))

    metadata_hint = ('-- Metadata size: %06d --\n' %
                     out_f.tell()).encode('ASCII')
    assert len(metadata_hint) == len(dummy_metadata_hint)
    out_f.seek(essential_metadata_size_hint_offset_to_patch)
    out_f.write(metadata_hint)
    out_f.seek(0, os.SEEK_END)

    # Write strile bytecounts and dummy offsets
    for idx_ifd, ifd in enumerate(ifds):
        tagdict = ifd.tagdict

        for id in tagdict:
            if id not in (TIFFTAG_STRIPOFFSETS, TIFFTAG_STRIPBYTECOUNTS,
                          TIFFTAG_TILEOFFSETS, TIFFTAG_TILEBYTECOUNTS):
                continue

            cur_pos = out_f.tell()
            out_f.seek(tagdict[id].fileoffset_in_out_ifd)
            out_f.write(struct.pack('<I', cur_pos))
            out_f.seek(cur_pos)
            if id in (TIFFTAG_STRIPOFFSETS, TIFFTAG_TILEOFFSETS):
                ifd.offset_out_offsets = out_f.tell()
                # dummy. to be rewritten
                out_f.write(b'\00' * len(tagdict[id].data))
            else:
                out_f.write(tagdict[id].data)  # bytecounts don't change

    # Write GDAL_METADATA of ifds other than the first one
    for ifd in ifds[1:]:
        tagdict = ifd.tagdict

        if TIFFTAG_GDAL_METADATA in tagdict:
            id = TIFFTAG_GDAL_METADATA
            cur_pos = out_f.tell()
            out_f.seek(tagdict[id].fileoffset_in_out_ifd)
            out_f.write(struct.pack('<I', cur_pos))
            out_f.seek(cur_pos)
            out_f.write(tagdict[id].data)

    nbands = 2 if args.do_not_write_error_samples else 4

    # Write first lat offset, long offset interleaved
    for ifd in ifds:
        tagdict = ifd.tagdict

        if TIFFTAG_STRIPOFFSETS in tagdict:
            ifd.num_striles = tagdict[TIFFTAG_STRIPOFFSETS].nvalues
            assert ifd.num_striles == tagdict[TIFFTAG_STRIPBYTECOUNTS].nvalues
            ifd.strile_offset_in = tagdict[TIFFTAG_STRIPOFFSETS].unpack_array()
            ifd.strile_length_in = tagdict[TIFFTAG_STRIPBYTECOUNTS].unpack_array(
            )
        else:
            ifd.num_striles = tagdict[TIFFTAG_TILEOFFSETS].nvalues
            assert ifd.num_striles == tagdict[TIFFTAG_TILEBYTECOUNTS].nvalues
            ifd.strile_offset_in = tagdict[TIFFTAG_TILEOFFSETS].unpack_array()
            ifd.strile_length_in = \
                tagdict[TIFFTAG_TILEBYTECOUNTS].unpack_array()

        assert (ifd.num_striles % nbands) == 0

        ifd.strile_offset_out = [0] * ifd.num_striles
        ifd.num_striles_per_band = ifd.num_striles // nbands
        for i in range(ifd.num_striles_per_band):
            for iband in (0, 1):
                idx_strile = ifd.num_striles_per_band * iband + i
                in_f.seek(ifd.strile_offset_in[idx_strile])
                data = in_f.read(ifd.strile_length_in[idx_strile])
                ifd.strile_offset_out[idx_strile] = out_f.tell()
                out_f.write(data)

    # And then the errors
    if nbands == 4:
        for ifd in ifds:
            tagdict = ifd.tagdict

            for i in range(ifd.num_striles_per_band):
                for iband in (2, 3):
                    idx_strile = ifd.num_striles_per_band * iband + i
                    in_f.seek(ifd.strile_offset_in[idx_strile])
                    data = in_f.read(ifd.strile_length_in[idx_strile])
                    ifd.strile_offset_out[idx_strile] = out_f.tell()
                    out_f.write(data)

    # Write strile offset arrays
    for ifd in ifds:
        tagdict = ifd.tagdict

        if TIFFTAG_STRIPOFFSETS in tagdict:
            tagtype = tagdict[TIFFTAG_STRIPOFFSETS].tagtype
        else:
            tagtype = tagdict[TIFFTAG_TILEOFFSETS].tagtype

        out_f.seek(ifd.offset_out_offsets)
        if tagtype == TIFF_SHORT:
            for v in ifd.strile_offset_out:
                assert v < 65536
                out_f.write(struct.pack('<H', v))
        else:
            for v in ifd.strile_offset_out:
                out_f.write(struct.pack('<I', v))

    # Patch pointer to last IFD
    out_f.seek(next_ifd_offset_out_offset)
    out_f.write(struct.pack('<I', 0))

    in_f.close()
    out_f.close()


if __name__ == '__main__':

    args = get_args()

    tmpfilename = args.dest + '.tmp'
    gdal.Unlink(tmpfilename)

    if not args.datetime and args.datetime != 'NONE':
        args.datetime = datetime.date.today().strftime("%Y-%m-%d %H:%M:%S")

    create_unoptimized_file(args.source, tmpfilename, args)
    generate_optimized_file(tmpfilename, args.dest, args)

    gdal.Unlink(tmpfilename)
