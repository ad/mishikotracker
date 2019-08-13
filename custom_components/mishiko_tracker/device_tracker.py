"""
device_tracker:
  - platform: mishikotracker
    username: 
    password:
    timezone: 3
"""
import logging, sys, json, time
from datetime import timedelta
import voluptuous as vol
from homeassistant.util import Throttle
import homeassistant.helpers.config_validation as cv
from homeassistant.components.device_tracker import PLATFORM_SCHEMA
from homeassistant.components.device_tracker.const import CONF_SCAN_INTERVAL, SCAN_INTERVAL, SOURCE_TYPE_ROUTER
from homeassistant import util
import aiohttp
__version__ = '1.0.0'
_LOGGER = logging.getLogger(__name__)

AUTH_URL = 'https://api2.mishiko.intech-global.com/profile/auth?email={}&pass={}&type=IOS'
PETS_URL = 'https://api2.mishiko.intech-global.com/devpet/list?timezone={}'
LOCATIONS_URL = 'https://api2.mishiko.intech-global.com/devpet/locations'

DOMAIN = 'mishikotracker'
CONF_USERNAME = 'email'
CONF_PASSWORD = 'password'
CONF_TIMEZONE = 'timezone'
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({vol.Required(CONF_USERNAME, default=''): cv.string, 
 vol.Required(CONF_PASSWORD, default=''): cv.string, 
 vol.Required(CONF_TIMEZONE): cv.positive_int})
CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({vol.Required(CONF_USERNAME, default=''): cv.string, 
          vol.Required(CONF_PASSWORD, default=''): cv.string, 
          vol.Required(CONF_TIMEZONE): cv.positive_int})},
  extra=(vol.ALLOW_EXTRA))


class Pet:
    def __init__(self, dev_id, dev_name, hass, config):
        self.hass = hass
        self.dev_id = dev_id
        self.host_name = dev_name

    def update(self, see, data):
        gps = (data['lat'], data['lon'])
        see(dev_id=self.dev_id, host_name=self.host_name, gps=gps, gps_accuracy=data['gps_accuracy'], battery=data['battery'], source_type=SOURCE_TYPE_ROUTER)
        return True


class MishikoTracker:

    def __init__(self, hass, config):
        self._hass = hass
        self.username = config['email']
        self.password = config['password']
        self.timezone = config['timezone']
        self.token = ''

    async def doAuth(self):
        if self.username != '':
            pass
        if self.password != '':
            try:
                url = AUTH_URL.format(self.username, self.password)
                headers = {'content-type':'application/json',  'X-SPOTTY-AUTH-NEW':'X-SPOTTY-AUTH-NEW'}
                async with aiohttp.ClientSession() as client:
                    async with client.get(url, headers=headers) as resp:
                        if not resp.status == 200:
                            raise AssertionError
                        info = await (resp.json())
                        self.token = resp.headers.get('X-SPOTTY-ACCESS-TOKEN')
            except Exception as error:
                try:
                    _LOGGER.warning('Could not auth %s - %s', self.username, error)
                finally:
                    error = None
                    del error

        else:
            _LOGGER.warning('email or password not provided')

    async def getPets(self):
        if self.token == '':
            await self.doAuth()

        try:
            url = PETS_URL.format(self.timezone)
            headers = {'content-type':'application/json',  'X-SPOTTY-AUTH-NEW':'X-SPOTTY-AUTH-NEW',  'X-SPOTTY-ACCESS-TOKEN':self.token}
            async with aiohttp.ClientSession() as client:
                async with client.get(url, headers=headers) as resp:
                    if resp.status == 401:
                        self.token = ''
                        time.sleep(10)
                        await self.getPets()
                        return
                    if not resp.status == 200:
                        raise AssertionError
                    
                    pets = await resp.json()

                    pets_info = {}
                    for pet in pets:
                        pets_info[pet['id']] = pet['name']
                    
                    return pets_info

        except Exception as error:
            try:
                _LOGGER.warning('Could not get pets %s - %s', self.username, error)
            finally:
                error = None
                del error


    async def getLocations(self):
        if self.token == '':
            await self.doAuth()

        try:
            url = LOCATIONS_URL
            headers = {'content-type':'application/json',  'X-SPOTTY-AUTH-NEW':'X-SPOTTY-AUTH-NEW',  'X-SPOTTY-ACCESS-TOKEN':self.token}
            async with aiohttp.ClientSession() as client:
                async with client.get(url, headers=headers) as resp:
                    if resp.status == 401:
                        self.token = ''
                        time.sleep(10)
                        await self.getLocations()
                        return
                    if not resp.status == 200:
                        raise AssertionError
                    
                    locations = await resp.json()

                    locations_info = {}
                    for location in locations['pets']:
                        locations_info[location['id']] = {'gps_accuracy': location['accuracy'], 'battery': location['batteryCharge'], 'lat': location['lat'],
        'lon': location['lon']}
                    
                    return locations_info
        except Exception as error:
            try:
                _LOGGER.warning('Could not get pets locations %s - %s', self.username, error)
            finally:
                error = None
                del error

async def setup_scanner(hass, config, see, discovery_info=None):
    hass.data[DOMAIN] = MishikoTracker(hass, config)

    await hass.data[DOMAIN].doAuth()

    _pets = await hass.data[DOMAIN].getPets()

    if _pets:
        pets = [Pet(dev_id, dev_name, hass, config) for (dev_id, dev_name) in _pets.items()]

        async def update_interval(hass, config):
            SCAN_INTERVAL = timedelta(seconds=60)
            interval = config.get(CONF_SCAN_INTERVAL, SCAN_INTERVAL)

            try:
                _locations = await hass.data[DOMAIN].getLocations()
                for pet in pets:
                    pet.update(see, _locations[pet.dev_id])
            finally:
                hass.helpers.event.async_track_point_in_utc_time(update_interval(hass, config), util.dt.utcnow() + SCAN_INTERVAL)

        await update_interval(hass, config)

    return True
