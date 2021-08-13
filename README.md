# h2bNh

This is Covering the Interl Hex format file to `Binary` or `C header` 


Usage: Simple command line interface for UPDI programming:
   or: cupdi [options] [[--] args]
   or: Erase chip: cupdi -c COM2 -d tiny817 -e
   or: Flash hex file: cupdi -c COM2 -d tiny817 --program -f c:/817.hex

Namespace(align='16', baseAddr='0x0', filename='', pad='0xFF', size='0x0', wcrc=False)
usage: Prog:  [-h] [-v] [-f [File Name]] [-a [Segment Base Address]]
              [-s [Generated Size]] [-p [Padded Value]] [--align [Text Align]]
              [--wcrc]

Covert Intel Hex format to `Binary` and `C Header`:
=================================================
Examples:

    <1> For pure hex(without segment): python h2bNh.py -f file.hex -a 0x8000 -s 0x3800 -p 0xFF
    <2> For segment included hex: python h2bNh.py -f file.hex

optional arguments:

  -h, --help            show this help message and exit  
  -v, --version         show version  
  -f [File Name], --filename [File Name]
			where the 'hex' file will be load
						
  -a [Segment Base Address], --baseAddr [Segment Base Address]
                        Used to appoint the Segment base address (will be
                        ignore if has EXT_SIGMENT_ADDR record)

  -s [Generated Size], --size [Generated Size]
                        Padded the output file, if this size larger than
                        actual data size(only support single segment)

  -p [Padded Value], --pad [Padded Value]
                        Padded value if the size argument is larger than
                        actual data size(will be ignore if size arg is not
                        appointed)

  --align [Text Align]  The text file will added \r every this number

  --wcrc                Indicate whether write CRC(24) to binary file, only
                        work when <size> large than <actual size> + 3