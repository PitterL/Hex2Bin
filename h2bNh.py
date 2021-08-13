import os
import sys
import argparse
import struct
import textwrap
from enum import Enum


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
                        action='version', version='%(prog)s [1.2.0]',
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

    parser.add_argument('-s', '--size', required=False,
                        nargs='?',
                        default='0x0',
                        metavar='Generated Size',
                        help='Padded the output file, if this size larger than actual data size(only support single segment)')

    parser.add_argument('-p', '--pad', required=False,
                        nargs='?',
                        default='0xFF',
                        metavar='Padded Value',
                        help='Padded value if the size argument is larger than actual data size(will be ignore if size arg is not appointed)')

    parser.add_argument('--align', required=False,
                        nargs='?',
                        default='16',
                        metavar='Text Align',
                        help='The text file will added \\r every this number')

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
        self.fpBinOut = None
        self.fpTextOut = None
        
        self.segSize = 0
        self.crc = 0
        self.segCount = 0
        self.alignText = 16

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


    def bin_segment_init(self, filename, addr):
        if self.fpBinOut:
            self.fpBinOut.close()
        
        newfile = "{filename}_0x{addr:04X}.bin".format(filename = filename, addr = addr)
        self.fpBinOut = open(newfile, 'wb')


    def text_segment_init(self, filename, addr):
        if self.fpTextOut:
            endseg = "}};\t/* {} bytes CRC(24) = 0x{:06X}*/\n".format(self.segSize, self.crc)
            self.fpTextOut.write(endseg)     
        else:
            newfile = "{filename}.h".format(filename = filename)
            self.fpTextOut = open(newfile, 'wt')
        
        if self.fpTextOut:
            newseg = "Sig_0x{addr:04X}[] = {{\n".format(addr = addr)
            self.fpTextOut.write(newseg)

    def segment_init(self, filename, addr):
        self.bin_segment_init(filename, addr)
        self.text_segment_init(filename, addr)

        self.segSize = 0
        self.crc = 0
        self.segCount += 1

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

    def segment_feed(self, hexstr):
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

    def sigment_pad(self, targetSize, pad, wcrc):
        # get memory to store crc24
        if wcrc:
            if not targetSize:
                targetSize = self.segSize + 3
            else:
                targetSize -= 3

        if self.segSize <= targetSize:
            size = targetSize - self.segSize

            if size > 0:
                count = size // self.alignText
                if count:
                    for i in range(count):
                        data = [pad] * self.alignText
                        self.sigment_feed_data(data)
                
                size = size % self.alignText
                if size:
                    data = [pad] * size
                    self.sigment_feed_data(data)

            if wcrc:
                data = list(self.crc.to_bytes(3, 'big'))
                self.sigment_feed_data(data, False)


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
        
        hexfile = args.filename
        
        align = int(args.align, 10)
        if align > 0:
            self.alignText = align

        if not os.path.exists(hexfile):
            print("File {} not exit.".format(hexfile))
            return

        try :
            # Open hex file
            fin = open(hexfile, 'r')
            if not fin:
                raise NameError('File `{}` Open failed'.format(hexfile))
            
            for hexstr in fin.readlines():
                hexstr = hexstr.strip()
                rectyp = self.peak_type(hexstr)
                if rectyp == ReocrdType.EXT_SIGMENT_ADDR.value:
                    #segment record
                    base = self.peak_data(hexstr, 0, 4)
                    addr = base << 4
                    # assert a new segment
                    self.segment_init(hexfile, addr)
                elif rectyp == ReocrdType.DATA_RECORD.value:
                    #data record
                    if not self.segCount:
                        addr = int(args.baseAddr, 16)
                        self.segment_init(hexfile, addr) # for none segment type hex
                    addr = int(args.baseAddr, 16)
                    self.segment_feed(hexstr)
                elif rectyp == ReocrdType.END_OF_FILE.value:
                    #end record
                    #check pad
                    size = int(args.size, 16)
                    pad = int(args.pad, 16)
                    wcrc = args.wcrc
                    if (self.segCount == 1):
                        self.sigment_pad(size, pad, wcrc)
                    
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
#cmd = r"-f fw.save".split()
#cmd = r"-f fw.hex -a 0x8000 -s 0x6000 --wcrc".split()
if __name__ == '__main__':
    main(cmd)
    print("end")
    