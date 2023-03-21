#!/usr/bin/python3
import smtplib
import time
from email.message import EmailMessage
import requests as req
import os
import subprocess
import configparser
import json
from typing import NamedTuple
import logging

# configparser properties
scriptDir = os.path.dirname(os.path.realpath(__file__))
config = configparser.ConfigParser()
config.read(f"{scriptDir}/settings.ini")
if len(config.sections()) == 0:
    config.read(f"/etc/minimal-monitoring/settings.ini")

# Defaults
MACHINE_IP = req.get("https://ifconfig.me").text
HOSTNAME = os.uname()[1]

# Sections in configparser
monitoring = config["MONITORING"]
mail = config["EMAIL"]
measurement = config["MEASUREMENT"]
logger = config["LOGGING"]

# Subsection (Logging attributes)
debugLevel = logger["debug_level"]
logName = logger["log_name"]
logDir = logger["log_dir"]
logPath = f"{logDir}/{logName}"

# Subsection (Monitoring attributes)
memory = monitoring['memory']
disk = monitoring['disk']
swap = monitoring['swap']

# Subsection (Mail attributes)
mailFrom = mail['from']
mailTo = json.loads(mail['to'])
mailSubject = mail['subject']
mailPort = mail['port']
mailHost = mail['host']

# Subsection (Measurement attributes)
usageThreshold = measurement['percent_threshold']


# Struct-like object to collect information in
# Unified format
class usageObject(NamedTuple):
    name: str
    total: int
    used: int
    available: int
    percentage: int
    alert: int
    additional: any


# Initializing logging
try:
    logging.basicConfig(filename=logPath, filemode='w', format='%(asctime)s [%(levelname)s] - %(message)s',
                        level=debugLevel)
except PermissionError as e:
    print(f"Could not create the log at - {logPath} due to lack of permissions")
    print(f"Please create the logfile with root and chown to the corresponding user! Exact error: \n {e}")
    exit(1)

# All usageObjects objects will be collected here for iteration in main()
allStats = []


def __sendMail(template: str) -> None:
    """
    Send mail function which requires only template.
    The rest of the attributes are fetched from settings.ini
    """
    logging.debug("We are in __sendMail()")
    msg = EmailMessage()
    msg.set_content(template)
    logging.debug(f"Using template: {template}")
    msg['Subject'] = mailSubject
    msg['From'] = mailFrom
    msg['To'] = ', '.join(mailTo)
    logging.debug(f"Email Attributes - {mailSubject}, {mailFrom}, {mailTo}")
    server = smtplib.SMTP(mailHost, port=int(mailPort))
    logging.info(f"Sending an email to - {mailTo}")
    try:
        server.send_message(msg)
        server.quit()
        logging.info("Successfully sent the email!")
    except Exception as error:
        logging.error(f"Failed to send the email due to: {error}")


def __appendToOverall(values: list) -> None:
    """
    Appends to the allStats list by building an object of usageObject()
    """
    logging.debug("We are in __appendToOverall()")
    for value in values:
        name, total, used, available, percentage, alert, *additional = value
        objectValues = usageObject(name, total, used, available, percentage, alert, additional)
        allStats.append(objectValues)


def __calcPercent(total, value) -> str:
    """
    Calculate the percentage between two values
    """
    logging.debug("We are in __calcPercent()")
    return str(round((int(value) / int(total)) * 100))


def __isCritical(usage, threshold) -> int:
    """
    Check if the usage is above or equal to the configured max threshold
    """
    logging.debug("We are in __isCritical()")
    return 1 if float(usage) >= int(threshold) else 0  # 1 is True fucking python


def __runCommand(command: str, delimiter: str = '\n') -> list:
    """
    Executes a shell command and returns the STDOUT in a 2D list.
    Each element in the list is a line of the STDOUT in list format.
    """
    logging.debug("We are in __runCommand()")
    output = subprocess.run(command, stdout=subprocess.PIPE, text=True, shell=True).stdout.split(delimiter)
    return [item.split() for item in output if item]  # skipping empty indexes


def memoryUsage() -> None:
    """
    Retrieves memory information by utilizing the "free" command.
    Afterward it calculates if the usage is critical and the percentage usage and append them to the values.
    All values are then merged into the usageObjects()
    """
    logging.debug("We are in memoryUsage()")
    if memory:
        cmd = "free -m | awk 'NR == 2 {print $2,$3,$4}'"
        values = __runCommand(cmd)
        for index in range(len(values)):
            values[index].append(__calcPercent(values[index][0], values[index][1]))  # Calculating percentage
            values[index].append(__isCritical(values[index][3], usageThreshold))  # Checking if threshold is hit
            values[index].insert(0, "memory")
        __appendToOverall(values)


def diskUsage() -> None:
    """
    Retrieves disk information by utilizing the "df" command.
    Afterward it calculates if the usage is critical and append it to values.
    All values are then merged into the usageObjects().
    It also contains "additional" information which is the partition name.
    """
    logging.debug("We are in diskUsage()")
    if disk:
        cmd = "df -h --output=source,size,used,avail,pcent | grep -vE '(tmp|loop)' | awk 'NR > 1 {print}' | tr -d '%'"
        values = __runCommand(cmd)
        for index in range(len(values)):
            values[index].append(__isCritical(values[index][4], usageThreshold))  # Checking if threshold is hit
            values[index].append(f"partition: {values[index].pop(0)}")
            values[index].insert(0, "disk")
        __appendToOverall(values)


def swapUsage() -> None:
    """
    Retrieves swap information by utilizing the "swapon" command.
    Afterward it calculates:
    - if the usage is critical
    - Calculate the usage in percents
    - Includes the partition name in the "additional" information
    All values are then merged into the usageObjects()
    """
    logging.debug("We are in swapUsage()")
    if swap:
        cmd = "swapon  --show --raw --bytes --show=name,size,used | awk 'NR > 1{print}'"
        values = __runCommand(cmd)
        for index in range(len(values)):
            values[index].append(int(values[index][1]) - int(values[index][2]))
            values[index].append(__calcPercent(values[index][1], values[index][2]))
            values[index].append(__isCritical(values[index][4], usageThreshold))
            values[index].append(f"partition: {values[index].pop(0)}")
            values[index].insert(0, "swap")


def sendMail(tmpl: usageObject) -> None:
    """
    Generates a template based on the usageObjects() and then calls the __sendMail function
    """
    logging.debug("We are inside sendMail()")
    template = f"""Hello,
    
It appears that the {tmpl.name} usage on {HOSTNAME} ({MACHINE_IP}) is critical!
    Total Size: {tmpl.total}
    Available Size: {tmpl.available}
    Used size: {tmpl.used}
    Usage in Percentage: {tmpl.percentage}
    Additional info:
    {tmpl.additional}

Please resolve immediately!
Cheers, 
Minimal Monitoring :)
"""
    logging.debug("Template has been generated in sendMail() will call __sendMail()")
    __sendMail(template)


def main():
    memoryUsage()
    diskUsage()
    swapUsage()
    logging.debug("Calling main()")
    for uObject in allStats:
        logging.debug("We are inside the main() - loop")
        if uObject.alert:
            logging.debug("Alert is true will call sendMail()")
            sendMail(uObject)


if __name__ == '__main__':
    while True:
        try:
            logging.info("Starting the script.")
            main()
        except Exception as mainError:
            logging.error(f"Main function threw and exception: {mainError}")
        time.sleep(600)

