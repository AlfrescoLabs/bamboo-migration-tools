#!/usr/bin/python

import requests
import sys

from lib.config import get_or_create as get_or_create_config
from lib.rest import REST_CONFIG_FIELDS, api_get, api_post

batch_size = 50
offset = 0

config = get_or_create_config('config.ini', 'bamboo', REST_CONFIG_FIELDS)
auth = (config['username'], config['password'])
base_path = config['url']

while True:
    try:
        r = api_get('/plan', {'expand': 'plans.plan.branches', 'max-result': batch_size, 'start-index': offset},
                    base_path=base_path, auth=auth)
        response_plans = r.json()['plans']
        plans = response_plans['plan']
        for plan in plans:
            try:
                export_resp = api_post('/export/plan/%s' % (plan['key'],), base_path=base_path, auth=auth).json()
                for export_resp_file in export_resp:
                    print('Written %s to %s' % (plan['key'], export_resp_file))
            except requests.exceptions.HTTPError as e:
                print(e)
        offset += batch_size
        if offset >= response_plans['size']:
            break
    except requests.exceptions.HTTPError as e:
        print(e)
