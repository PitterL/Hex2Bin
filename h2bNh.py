'''
MIT License

Copyright (c) [2022] [Microchip]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

import os
import sys
import argparse
import struct
import textwrap
from enum import Enum

'''
     Introducing a handy tool convert hex file to binary file or C arrays. Which can convert hex to segment binary/array or a single one. 
        We all know the fuse/config bits are in a much higher address, usually make general tools generate a huge file. Now this tool helps.
        
    Version:
        <1.2.1>: Intitilized, support avr hex
        <1.2.2>: support pic type hex: <a> Extended Linear Address Record <b> uncontinous data record
        <1.2.3>: support uncontinous data record simulated a new Segment for PIC
'''

def parse_args(args=None):
    parser = argparse.ArgumentParser(
        prog='Prog: ',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        ##formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description=textwrap.dedent('''
        Covert Intel Hex format to Binary and `c` Header:
        =================================================
        Examples:
            <1> For pure hex(without segment): python h2bNh.py -f file.hex -a 0x8000 -s 0x3800 -p 0xFF
            <2> For segment included hex: python h2bNh.py -f file.hex
        '''))

    parser.add_argument('-v', '--version',
                        action='version', version='%(prog)s [1.2.3]',
                        help='show version')
                        

    parser.add_argument('-f', '--filename', required=False,
                        nargs='?',
                        default='',
                        metavar='File Name',
                        help='where the \'hex\' file will be load')

    parser.add_argument('-a', '--baseAddr', required=False,
                        nargs='?',
                        default='0x0',
                        metavar='Segment Base Address',
                        help='Used to appoint the Segment base address (will be ignore if has EXT_SIGMENT_ADDR record)')

    parser.add_argument('-s', '--sigmentTargetSize', required=False,
                        nargs='?',
                        default='0x0',
                        metavar='The Generated Size of a Sigment',
                        help='Padded the output file, if this size larger than actual data size(only support single segment, Hex)')

    parser.add_argument('-p', '--pad', required=False,
                        nargs='?',
                        default='0xFF',
                        metavar='Padded Value',
                        help='Padded value(hex) if the size argument is larger than actual data size(will be ignore if size arg is not appointed)')

    parser.add_argument('-', '--gapSimSeg', required=False,
                        nargs='?',
                        default='0',
                        metavar='Gap to simulate a New Segment',
                        help='Determine how much gap between two address will be split into different segments (Dec)')

    parser.add_argument('--align', required=False,
                        nargs='?',
                        default='16',
                        metavar='Text Align',
                        help='Determine output the C Array line width, that will added \`\\r\` every this count (Dec)')

    parser.add_argument('--wcrc', required=False,
                        default=False,
                        action='store_true',
                        #metavar='Write CRC',
                        help='Indicate whether write CRC(24) to binary file, only work when <size> large than <actual size> + 3')

    return parser


class ReocrdType(Enum):
    DATA_RECORD = 0x0
    END_OF_FILE = 0x01
    EXT_SIGMENT_ADDR = 0x02
    START_SEGMENT_ADDR = 0x03
    EXT_LINEAR_ADDR = 0x04
    START_LINEAR_ADDR = 0x05


class H2B:
    
    def __init__(self):
        self.fileName = ''
        self.fpBinOut = None
        self.fpTextOut = None
        self.padValue = 0xff

        self.newSeg = False
        self.baseAddr = 0
        self.segSize = 0
        self.crc = 0
        self.segCount = 0
        self.alignText = 16
        self.dataOffset = 0
        self.gapSimSeg = 0

    def _set_offset(self, offset):
        self.dataOffset = offset

    def _peak(self, hexstr, st, size):
        return int(hexstr[st : st + size], 16)

    def peak_off(self, hexstr, off, idx, size):
        return self._peak(hexstr, off + idx * size, size)

    def peak_head(self, hexstr, idx, size):
        return self._peak(hexstr, 1 + idx * size, size)
    
    def peak_len(self, hexstr):
        return self._peak(hexstr, 1, 2)
    
    def peak_offset(self, hexstr):
        return self._peak(hexstr, 3, 4)

    def peak_type(self, hexstr):
        return self._peak(hexstr, 7, 2)
    
    def peak_data(self, hexstr, idx, size):
        return self._peak(hexstr, 9 + idx * size, size)

    def peak_checksum(self, hexstr):
        size = self.peak_len(hexstr)
        return self._peak(hexstr, 9 + size * 2, 2)

    def crc24(self, crc, firstbyte, secondbyte):
        crcpoly = 0x80001B
        data_word = (secondbyte << 8) | firstbyte
        result = ((crc << 1) ^ data_word)

        if result & 0x1000000:
            result ^= crcpoly

        return result
    
    """
        Calculate buffer with crc24
            @base: buffer input
            @returns calculated crc value, only bit[0~23] is valid
    """
    def calc_crc24(self, crc, base):
        data = base.copy()

        # if len is odd, fill the last byte with 0 
        if len(data) & 0x1:
            data.append(0)

        for i in range(0, len(data), 2):
            crc = self.crc24(crc, data[i], data[i + 1])

        # Mask to 24-bit
        crc &= 0x00FFFFFF

        return crc


    def _bin_segment_save_and_create(self, filename, base, offset):
        if self.fpBinOut:
            self.fpBinOut.close()
        
        newfile = "{filename}_Sig_0x{base:04X}_({off:04X}h).bin".format(filename = filename, base = base, off = offset)
        self.fpBinOut = open(newfile, 'wb')


    def _text_segment_save_and_create(self, filename, base, offset):
        if self.fpTextOut:
            endseg = "}};\t/* {} bytes CRC(24) = 0x{:06X}*/\n".format(self.segSize, self.crc)
            self.fpTextOut.write(endseg)
        else:
            newfile = "{filename}.h".format(filename = filename)
            self.fpTextOut = open(newfile, 'wt')
        
        if self.fpTextOut:
            newseg = "Sig_0x{base:04X}_({off:04X}h)[] = {{\n".format(base = base, off = offset)
            self.fpTextOut.write(newseg)


    def segment_save_and_create(self, offset = 0):
        self._text_segment_save_and_create(self.fileName, self.baseAddr, offset)
        self._bin_segment_save_and_create(self.fileName, self.baseAddr, offset)
        
        self.crc = 0
        self.segSize = 0
        self.segCount += 1
        self.dataOffset = 0
        self.newSeg = False

    def segment_init(self, baseaddr):
        self.newSeg = True
        self.baseAddr = baseaddr


    def bin_feed(self, data):
        if self.fpBinOut:
            for v in data:
                binary = struct.pack('B', v)
                self.fpBinOut.write(binary)
    

    def text_feed(self, data):
        if self.fpTextOut:
            for (i, v) in enumerate(data):
                if self.alignText and not (self.segSize + i) % self.alignText:
                    self.fpTextOut.write("\t"*2)

                text = "0x{:02X}, ".format(v)
                self.fpTextOut.write(text)
                
                if self.alignText and not (self.segSize + i + 1) % self.alignText:
                    self.fpTextOut.write("\n")


    def sigment_feed_data(self, data, calCrc=True):
        self.bin_feed(data)
        self.text_feed(data)

        self.segSize += len(data)
        
        if calCrc:
            self.crc = self.calc_crc24(self.crc, data)


    def sigment_pad_begin(self, offset):
        if self.newSeg:
            self.segment_save_and_create(offset)
        else:
            gapsize = offset - self.dataOffset
            # Test whehter simulate a new Segment
            if self.gapSimSeg and gapsize >= self.gapSimSeg:
                self.segment_save_and_create(offset)
            else:
                self.sigment_pad(gapsize)


    def segment_feed(self, hexstr):
        # offset
        offset = self.peak_offset(hexstr)
        self.sigment_pad_begin(offset)

        # size
        size = self.peak_len(hexstr)
        
        data = []
        chksum = 0

        for i in range(4):
            v = self.peak_head(hexstr, i, 2)
            chksum += v

        for i in range(size):
            v = self.peak_data(hexstr, i, 2)
            
            chksum += v
            data.append(v)
        
        # checksum
        checksum = self.peak_checksum(hexstr)
        # all bytes data should be Zero with check sum
        if (checksum + chksum) & 0xFF:
            raise NameError('Error: Checksum mismatch at {}'.format(hexstr))
        
        if size:
            self.sigment_feed_data(data)
        
        self._set_offset(offset + size)
    

    def _sigment_pad(self, size, pad):
        if size <= 0:
            return

        count = size // self.alignText
        if count:
            for i in range(count):
                data = [pad] * self.alignText
                self.sigment_feed_data(data)
        
        size = size % self.alignText
        if size:
            data = [pad] * size
            self.sigment_feed_data(data)


    def sigment_pad(self, size):
        self._sigment_pad(size, self.padValue)


    def sigment_crc(self):
        data = list(self.crc.to_bytes(3, 'big'))
        self.sigment_feed_data(data)


    def bin_end(self):
        if self.fpBinOut:
            self.fpBinOut.close()
            self.fpBinOut = None
    

    def text_end(self):
        if self.fpTextOut:
            endseg = "}};\t/* {} bytes CRC(24) = 0x{:06X}*/\n".format(self.segSize, self.crc)
            self.fpTextOut.write(endseg)
            self.fpTextOut.close()
            self.fpBinOut = None


    def segment_end(self):
        self.bin_end()
        self.text_end()


    def run(self, args):
        fin = None
        
        # check file whether existed
        hexfile = args.filename
        if not os.path.exists(hexfile):
            print("File {} not exit.".format(hexfile))
            return

        # pad
        self.padValue = int(args.pad, 16)
        # align
        align = int(args.align, 10)
        if align > 0:
            self.alignText = align
        # gap to simulated a new segment
        self.gapSimSeg = int(args.gapSimSeg, 10)

        try :
            # Open hex file
            fin = open(hexfile, 'r')
            if not fin:
                raise NameError('File `{}` Open failed'.format(hexfile))
            else:
                self.fileName = hexfile
                
            for hexstr in fin.readlines():
                hexstr = hexstr.strip()
                rectyp = self.peak_type(hexstr)
                if rectyp == ReocrdType.EXT_SIGMENT_ADDR.value:
                    #segment record
                    base = self.peak_data(hexstr, 0, 4)
                    addr = base << 4
                    # assert a new segment
                    self.segment_init(addr)
                if rectyp == ReocrdType.EXT_LINEAR_ADDR.value:
                    #Linear record
                    base = self.peak_data(hexstr, 0, 4)
                    addr = base << 8
                    # assert a new segment
                    self.segment_init(addr)
                elif rectyp == ReocrdType.DATA_RECORD.value:
                    #data record
                    if not self.segCount:
                        addr = int(args.baseAddr, 16)
                        self.segment_init(addr) # for none segment type hex
                    self.segment_feed(hexstr)
                elif rectyp == ReocrdType.END_OF_FILE.value:
                    #end record
                    targetSize = int(args.sigmentTargetSize, 16)
                    wcrc = args.wcrc
                    if (self.segCount == 1):
                        padSize = targetSize - self.segCount
                        if (wcrc):
                            padSize -= 3    # space for crc24
                        self.sigment_pad(padSize)

                        if (wcrc):
                            self.sigment_crc()

                    self.segment_end()
        except Exception as e:
            print(e)
        finally:
            if fin:
                fin.close()

def main(args = None):
    parser = parse_args(args)
    aargs = args if args is not None else sys.argv[1:]
    args = parser.parse_args(aargs)
    print(args)
    
#    if not args.filename and not args.type:
    if not args.filename:
        parser.print_help()
        return

    fn = H2B()
    fn.run(args)

cmd = None
#cmd = r"-f example\avr\fw.save".split()
#cmd = r"-f example\avr\fw.hex -a 0x8000 -s 0x6000 --align 32 --wcrc".split()
#cmd = r"-f example\pic\Q84.hex --gapSimSeg 64".split()
if __name__ == '__main__':
    main(cmd)
    print("end")
    