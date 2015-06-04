import urllib, urllib2
import re
import getopt
import sys

trips_url = 'http://trips.ihmc.us/parser/cgi/drum'

def send_query(text, query_args={}):
    query_args['input'] = text
    data = urllib.urlencode(query_args)
    req = urllib2.Request(trips_url,data)
    res = urllib2.urlopen(req)
    html = res.read()
    return html

def get_xml(html):
    ekb = re.findall(r'<ekb .*?>(.*?)</ekb>',html,re.MULTILINE|re.DOTALL)
    if ekb:
        events_terms = ekb[0]
    else:
        events_terms = ''
    header = '<?xml version="1.0" encoding="utf-8" standalone="yes"?><extractions>'
    footer = '</extractions>'
    return header + events_terms + footer

def save_xml(xml,file_name):
    try:
        fh = open(file_name,'wt')
    except IOError:
        print 'Could not open %s for writing.' % file_name
        return
    fh.write(xml)
    fh.close()

if __name__ == '__main__':
    filemode = False
    text = 'Active BRAF phosphorylates MEK1 at Ser222.'
    outfile_name = 'braf_test.xml'

    opts, extraparams = getopt.getopt(sys.argv[1:],'s:f:o:h',['string=','file=','output=','help'])
    for o,p in opts:
        if o in ['-h','--help']:
            print 'String mode: python trips_client.py --string "RAS binds GTP" --output text.xml'
            print 'File mode: python trips_client.py --file test.txt --output text.xml'
            sys.exit()
        elif o in ['-s','--string']:
            text = p
        elif o in ['-f','--file']:
            filemode = True
            infile_name = p
        elif o in ['-o','--output']:
            outfile_name = p
    
    if filemode:
        try:
            fh = open(infile_name,'rt')
        except IOError:
            print 'Could not open %s.' % infile_name
            exit()
        text = fh.read()
        fh.close()
        print 'Parsing contents of %s...' % infile_name
    else:
        print 'Parsing string: %s' % text
    
    html = send_query(text)
    xml = get_xml(html)
    save_xml(xml,outfile_name)
