#!/usr/bin/python

import csv
import requests
import sys

from lib.config import get_or_create as get_or_create_config
from lib.rest import REST_CONFIG_FIELDS, api_get

batch_size = 50
offset = 0

config = get_or_create_config('config.ini', 'bamboo', REST_CONFIG_FIELDS)
auth = (config['username'], config['password'])
base_path = config['url']
writer = csv.writer(sys.stdout)

while True:
    try:
        r = api_get('/plan', {'expand': 'plans.plan.branches', 'max-result': batch_size, 'start-index': offset},
                    base_path=base_path, auth=auth)
        response_plans = r.json()['plans']
        plans = response_plans['plan']
        for plan in plans:
            writer.writerow([plan['project']['key'], plan['project']['name'], plan['key'], plan['shortName'], plan['enabled'],])
        offset += batch_size
        if offset >= response_plans['size']:
            break
    except requests.exceptions.HTTPError as e:
        print(e)
        break
