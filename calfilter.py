import icalendar
from icalevents.icalevents import events
import logging

ICAL_FILE = "./work.ics"
FILTER_PHRASES = ["OOF", "Blocked"]

DEBUG_EVENT_COUNT = 10

def filter_events_by_keyword(cal : icalendar.Calendar) -> icalendar.Calendar:
    filtered = 0

    for event in cal.walk("VEVENT"):
        for phrase in FILTER_PHRASES:
            if phrase in event.get('SUMMARY'):
                logging.debug(f"Filtering event: {event.get('summary')}")
                cal.subcomponents.remove(event)
                filtered += 1

    if filtered > 0:
        logging.debug(f"Filtered {filtered} events")

    return cal

def main():
    logging.basicConfig(level=logging.DEBUG)
    new_cal = None
    with open(ICAL_FILE, 'rb') as f:
        cal = icalendar.Calendar.from_ical(f.read())
        new_cal = filter_events_by_keyword(cal)

    for (i, event) in enumerate(new_cal.walk("VEVENT")):
        if i > DEBUG_EVENT_COUNT:
            break
        logging.debug(event.get('summary'))

if __name__ == "__main__":
    main()