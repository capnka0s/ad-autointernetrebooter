import appdaemon.plugins.hass.hassapi as hass
from datetime import datetime, time

#
# Auto Crappy Internet Rebooter
# Developed by @UbhiTS on GitHub
#
# Args:
#internet_health_monitor:
#  module: auto_internet_rebooter
#  class: AutoInternetRebooter
#  internet:
#    download: sensor.speedtest_download
#    upload: sensor.speedtest_upload
#    ping: sensor.speedtest_ping
#    switch: switch.garage_internet_switch
#  thresholds:
#    download_mbps: 50.0
#    upload_mbps: 3.5
#    ping_ms: 75
#    unavailable_is_error: false
#  delays:
#    reboot_delay_s: 30
#    off_duration_s : 15
#  schedule:
#    - "04:00:00"
#    - "16:00:00"
#  notify:
#    alexa: media_player.upper_big_bedroom_alexa
#    start_time: "08:00:00"
#    end_time: "21:30:00"
#  debug: false
#  dryrun: false

DEFAULT_REBOOT_DELAY_S=30
DEFAULT_OFF_DURATION_S=15
DEFAULT_UNAVAILABLE_IS_ERROR="false"

class AutoInternetRebooter(hass.Hass):

  def initialize(self):
    self.reboot_delay_s = DEFAULT_REBOOT_DELAY_S
    self.off_duration = DEFAULT_OFF_DURATION_S

    self.debug = True;
    self.dryrun = False;
    self.sensor_download = self.args["internet"]["download"]
    self.sensor_upload = self.args["internet"]["upload"]
    self.sensor_ping = self.args["internet"]["ping"]
    self.switch = self.args["internet"]["switch"]

    self.threshold_download = float(self.args["thresholds"]["download_mbps"])
    self.threshold_upload = float(self.args["thresholds"]["upload_mbps"])
    self.threshold_ping = float(self.args["thresholds"]["ping_ms"])

    self.schedule = self.args["schedule"]
    
    self.unavailable_is_error = self.args.get('unavailable_is_error', DEFAULT_UNAVAILABLE_IS_ERROR).lower() == 'true'

    self.notify = False

    if "notify" in self.args:
      self.notify = True
      self.alexa = self.args["notify"]["alexa"]
      self.notify_start_time = datetime.strptime(self.args["notify"]["start_time"], '%H:%M:%S').time()
      self.notify_end_time = datetime.strptime(self.args["notify"]["end_time"], '%H:%M:%S').time()

    if "delays" in self.args:
      self.reboot_delay_s = float(self.args["delays"].get("reboot_delay_s", DEFAULT_REBOOT_DELAY_S))
      self.off_duration_s = float(self.args["delays"].get("off_duration_s", DEFAULT_OFF_DURATION_S))


    for schedule in self.schedule:
      time = datetime.strptime(schedule, '%H:%M:%S').time()
      self.run_daily(self.run_speedtest, time)

    # subscribe to value changes
    self.listen_state(self.evaluate_internet_health, self.sensor_ping, attribute = "state")
    self.listen_state(self.evaluate_internet_health, self.sensor_download, attribute = "state")
    self.listen_state(self.evaluate_internet_health, self.sensor_upload, attribute = "state")

    self.debug_log(f"\n**** INIT - AUTO 'CRAPPY INTERNET' REBOOTER ****\n"
                   f"  D/L  {self.threshold_download}\n"
                   f"  U/L   {self.threshold_upload}\n"
                   f"  PING {self.threshold_ping}\n"
                   f"  REBOOT_DELAY {self.reboot_delay_s}\n"
                   f"  OFF_DURATION {self.off_duration_s}\n"
                   )

    self.debug = bool(self.args["debug"]) if "debug" in self.args else self.debug
    self.dryrun = bool(self.args["dryrun"]) if "dryrun" in self.args else self.dryrun


  def run_speedtest(self, kwargs):
    self.debug_log("INTERNET SPEED TEST IN PROGRESS")
    try:
      # in try catch as this seems to be a synchronous call. AppDaemon timesout!
      self.call_service("speedtestdotnet/speedtest")
    except Exception as e:
      self.debug_log(f"ERROR RUNNING SPEED TEST: {e}")


  def evaluate_internet_health(self, entity, attribute, old, new, kwargs):
    
    connection_error = self.get_state(self.sensor_download) == 'unavailable'
    
    speed_download = None
    speed_upload = None
    speed_ping = None
    
    try:
      speed_download = float(self.get_state(self.sensor_download))
      speed_upload = float(self.get_state(self.sensor_upload))
      speed_ping = float(self.get_state(self.sensor_ping))
    except: pass

    d = speed_download and speed_download < self.threshold_download
    u = speed_upload and speed_upload < self.threshold_upload
    p = speed_ping and speed_ping > self.threshold_ping
    e = connection_error and self.unavailable_is_error

    if d or u or p or e:
      log = []
      if d: log += [f"D/L {self.threshold_download}|{speed_download}"]
      if u: log += [f"U/L {self.threshold_upload}|{speed_upload}"]
      if p: log += [f"PING {self.threshold_ping}|{speed_ping}"]
      if e: log += [f"ERROR {self.unavailable_is_error}|{connection_error}"]
      self.debug_log("INTERNET HEALTH ERROR: " + ", ".join(log))
      self.debug_log(f"INTERNET POWER CYCLE IN {self.reboot_delay_s} SECS, OFF FOR {self.off_duration_s} SECS")

      if self.notify and self.is_time_okay(self.notify_start_time, self.notify_end_time):
        self.call_service("notify/alexa_media", data = {"type":"tts", "method":"all"}, target = self.alexa, message = "Your attention please, internet power cycle in {self.reboot_delay_s} seconds!")

      self.run_in(self.turn_off_switch, self.reboot_delay_s)
      self.run_in(self.turn_on_switch, self.reboot_delay_s+self.off_duration_s)
    else:
      self.debug_log("INTERNET SPEED TEST IS OK")

  def call_service_dry_run(self, service_name, entity_id):
    if not self.dryrun:
      self.call_service(service_name, entity_id = self.switch)
    else:
      self.debug_log(f"DRY RUN: call_service('{service_name}', entity_id={entity_id})")


  def turn_off_switch(self, kwargs):
    self.debug_log("INTERNET RESET : TURN OFF")
    self.call_service_dry_run("switch/turn_off", entity_id = self.switch)


  def turn_on_switch(self, kwargs):
    self.debug_log("INTERNET RESET : TURN ON")
    self.call_service_dry_run("switch/turn_on", entity_id = self.switch)


  def is_time_okay(self, start, end):
    current_time = datetime.now().time()
    if (start < end):
      return start <= current_time and current_time <= end
    else:
      return start <= current_time or current_time <= end


  def debug_log(self, message):
    if self.debug:
      self.log(message)
