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
    return parser.parse_args()


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

    for idx_ifd, subds in enumerate(subdatsets):
        src_ds = gdal.Open(subds[0])
        assert src_ds.GetMetadataItem('GS_TYPE') == 'SECONDS'

        tmp_ds = gdal.GetDriverByName('GTiff').Create('/vsimem/tmp',
                                                      src_ds.RasterXSize,
                                                      src_ds.RasterYSize,
                                                      nbands,
                                                      gdal.GDT_Float32)
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

        data = src_ds.GetRasterBand(1).ReadRaster()
        tmp_ds.GetRasterBand(1).WriteRaster(0, 0, src_ds.RasterXSize, src_ds.RasterYSize,
                                            data)
        tmp_ds.GetRasterBand(1).SetDescription('latitude_offset')
        tmp_ds.GetRasterBand(1).SetUnitType('arc-second')

        data = src_ds.GetRasterBand(2).ReadRaster()
        tmp_ds.GetRasterBand(2).WriteRaster(0, 0, src_ds.RasterXSize, src_ds.RasterYSize,
                                            data)
        tmp_ds.GetRasterBand(2).SetDescription('longitude_offset')
        tmp_ds.GetRasterBand(2).SetUnitType('arc-second')

        if nbands == 4:
            data = src_ds.GetRasterBand(3).ReadRaster()
            tmp_ds.GetRasterBand(3).WriteRaster(0, 0, src_ds.RasterXSize, src_ds.RasterYSize,
                                                data)
            tmp_ds.GetRasterBand(3).SetDescription('latitude_offset_accuracy')
            tmp_ds.GetRasterBand(3).SetUnitType('metre')

            data = src_ds.GetRasterBand(4).ReadRaster()
            tmp_ds.GetRasterBand(4).WriteRaster(0, 0, src_ds.RasterXSize, src_ds.RasterYSize,
                                                data)
            tmp_ds.GetRasterBand(4).SetDescription('longitude_offset_accuracy')
            tmp_ds.GetRasterBand(4).SetUnitType('metre')

        dst_crs = osr.SpatialReference()
        dst_crs.SetFromUserInput(args.target_crs)
        dst_auth_name = dst_crs.GetAuthorityName(None)
        dst_auth_code = dst_crs.GetAuthorityCode(None)
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
                desc += os.path.basename(args.source)

            tmp_ds.SetMetadataItem('TIFFTAG_IMAGEDESCRIPTION', desc)
            tmp_ds.SetMetadataItem('TIFFTAG_COPYRIGHT', args.copyright)

        options = ['PHOTOMETRIC=MINISBLACK',
                   'COMPRESS=DEFLATE',
                   'PREDICTOR=3',
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
    first_ifd_offset = next_ifd_offset

    out_f = open(destfilename, 'wb')
    out_f.write(signature)
    next_ifd_offset_out_offset = 4
    # placeholder for pointer to next IFD
    out_f.write(struct.pack('<I', 0xDEADBEEF))

    out_f.write(b'\n-- Generated by ntv2_to_gtiff.py v1.0 --\n')

    ifds = []

    while next_ifd_offset != 0:

        in_f.seek(next_ifd_offset, os.SEEK_SET)

        cur_pos = out_f.tell()
        if (cur_pos % 2) == 1:
            out_f.write(b'\x00')
            cur_pos += 1
        out_f.seek(next_ifd_offset_out_offset, os.SEEK_SET)
        out_f.write(struct.pack('<I', cur_pos))
        out_f.seek(cur_pos, os.SEEK_SET)

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
                in_f.seek(tagvalueoroffset, os.SEEK_SET)
                tagdata = in_f.read(tagvalsize)
                in_f.seek(curinoff, os.SEEK_SET)
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
            out_f.seek(tagdict[id].fileoffset_in_out_ifd, os.SEEK_SET)
            out_f.write(struct.pack('<I', cur_pos))
            out_f.seek(cur_pos, os.SEEK_SET)
            out_f.write(tagdict[id].data)

        ifds.append(IFD(tagdict))

    # Write strile bytecounts and dummy offsets
    for idx_ifd, ifd in enumerate(ifds):
        tagdict = ifd.tagdict

        for id in tagdict:
            if id not in (TIFFTAG_STRIPOFFSETS, TIFFTAG_STRIPBYTECOUNTS,
                          TIFFTAG_TILEOFFSETS, TIFFTAG_TILEBYTECOUNTS):
                continue

            cur_pos = out_f.tell()
            out_f.seek(tagdict[id].fileoffset_in_out_ifd, os.SEEK_SET)
            out_f.write(struct.pack('<I', cur_pos))
            out_f.seek(cur_pos, os.SEEK_SET)
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
            out_f.seek(tagdict[id].fileoffset_in_out_ifd, os.SEEK_SET)
            out_f.write(struct.pack('<I', cur_pos))
            out_f.seek(cur_pos, os.SEEK_SET)
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
                in_f.seek(ifd.strile_offset_in[idx_strile], os.SEEK_SET)
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
                    in_f.seek(ifd.strile_offset_in[idx_strile], os.SEEK_SET)
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

        out_f.seek(ifd.offset_out_offsets, os.SEEK_SET)
        if tagtype == TIFF_SHORT:
            for v in ifd.strile_offset_out:
                assert v < 65536
                out_f.write(struct.pack('<H', v))
        else:
            for v in ifd.strile_offset_out:
                out_f.write(struct.pack('<I', v))

    # Patch pointer to last IFD
    out_f.seek(next_ifd_offset_out_offset, os.SEEK_SET)
    out_f.write(struct.pack('<I', 0))

    in_f.close()
    out_f.close()


if __name__ == '__main__':

    args = get_args()

    tmpfilename = args.dest + '.tmp'
    gdal.Unlink(tmpfilename)

    create_unoptimized_file(args.source, tmpfilename, args)
    generate_optimized_file(tmpfilename, args.dest, args)

    gdal.Unlink(tmpfilename)