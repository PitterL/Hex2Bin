import os
import sys
import argparse
import struct

def parse_args(args=None):
    parser = argparse.ArgumentParser(
        prog='hex to bin and htxt',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Examples: python h2bNh -f D:\\file.hex -s 0x3800')

    parser.add_argument('--version',
                        action='version', version='%(prog)s v1.0.1',
                        help='show version')
                        

    parser.add_argument('-f', '--filename', required=True,
                        nargs='?',
                        default='',
                        metavar='hex',
                        help='where the \'hex\' file will be load')

    return parser

class H2B:
    
    def __init__(self):
        self.fpBinOut = None
        self.fpTextOut = None
        self.segSize = 0
        self.crc = 0

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


    def bin_segment_init(self, filename, name):
        if self.fpBinOut:
            self.fpBinOut.close()
        
        newfile = "{filename}_{name}.bin".format(filename = filename, name = name)
        self.fpBinOut = open(newfile, 'wb')


    def text_segment_init(self, filename, name):
        if self.fpTextOut:
            endseg = "}};\t/* {} bytes CRC(24) = 0x{:06X}*/\n".format(self.segSize, self.crc)
            self.fpTextOut.write(endseg)     
        else:
            newfile = "{filename}.h".format(filename = filename)
            self.fpTextOut = open(newfile, 'wt')
        
        if self.fpTextOut:
            newseg = "Sig_{name}[] = {{\n".format(name = name)
            self.fpTextOut.write(newseg)

    def segment_init(self, filename, name):
        self.bin_segment_init(filename, name)
        self.text_segment_init(filename, name)

        self.segSize = 0
        self.crc = 0

    def bin_feed(self, data):
        if self.fpBinOut:
            for v in data:
                binary = struct.pack('B', v)
                self.fpBinOut.write(binary)
    
    def text_feed(self, data):
        if self.fpTextOut:
            self.fpTextOut.write("\t"*2)
            for v in data:
                text = "0x{:02X}, ".format(v)
                self.fpTextOut.write(text)

            self.fpTextOut.write("\n")

    def segment_feed(self, hexstr):
        # size
        size = int(hexstr[1 : 3], 16)
        
        data = []
        chksum = 0

        for i in range(4):
            st = 1 + i * 2 
            v = int(hexstr[st : st + 2], 16)
            chksum += v
            
        for i in range(size):
            st = 9 + i * 2 
            v = int(hexstr[st : st + 2], 16)
            
            chksum += v
            data.append(v)
        
        # checksum
        st += 2
        checksum = int(hexstr[st: st + 2], 16)
        # all bytes data should be Zero with check sum
        if (checksum + chksum) & 0xFF:
            raise NameError('Error: Checksum mismatch at {}'.format(hexstr))
        
        if size:
            self.bin_feed(data)
            self.text_feed(data)
            self.segSize += size
            self.crc = self.calc_crc24(self.crc, data)
    
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

    def run(self, hexfile):
        fin = None
        
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
                rectyp = int(hexstr[7 : 9], 16)
                if rectyp == 0x02:
                    #segment record
                    base = int(hexstr[9 : 13],16)
                    addr = base << 4
                    # assert a new segment
                    self.segment_init(hexfile, hex(addr))
                elif rectyp == 0x0:
                    #data record
                    self.segment_feed(hexstr)
                elif rectyp == 0x01:
                    #end record
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
        
    inputfile = args.filename

    fn = H2B()
    fn.run(inputfile)

cmd = None
#cmd = r"-f fw.save".split()
if __name__ == '__main__':
    main(cmd)
    print("end")
    