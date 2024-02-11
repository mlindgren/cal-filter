import icalendar
import icalevents.icalevents as icalevents
import logging

from thefuzz import fuzz

PRIMARY_ICAL_FILE = "./personal.ics"
TARGET_ICAL_FILE = "./work.ics"
FILTER_PHRASES = ["OOF", "Blocked"]

DEBUG_EVENT_COUNT = 10

def filter_duplicates(primary_calender_content : str, target_calendar : icalendar.Calendar) -> None:
    """
    Filters events from the target calendar that are already in the primary calendar.
    Due to the way the icalevents module works, the primary calendar is passed as a string and re-parsed every time :/
    See https://github.com/jazzband/icalevents/issues/130

    primary_calender_content: The iCalendar content of the primary calendar as a string
    target_calendar: The target calendar to filter
    """

    filtered = 0
    for event in target_calendar.walk("VEVENT"):
        result = icalevents.events(
            string_content = primary_calender_content,
            start = event.get('DTSTART').dt,
            end = event.get('DTEND').dt,
            sort = True)
        
        if len(result) > 0:
            if fuzz.partial_ratio(event.get('SUMMARY'), result[0]['summary']) > 90:
                logging.debug(f"Filtering event: {event.get('summary')}")
                target_calendar.subcomponents.remove(event)
                filtered += 1

                continue

def filter_events_by_keyword(cal : icalendar.Calendar) -> None:
    """
    Filters events from the calendar that contain any of the FILTER_PHRASES.

    cal: The calendar to filter
    """
    filtered = 0

    for event in cal.walk("VEVENT"):
        for phrase in FILTER_PHRASES:
            if phrase in event.get('SUMMARY'):
                logging.debug(f"Filtering event: {event.get('summary')}")
                cal.subcomponents.remove(event)
                filtered += 1

    if filtered > 0:
        logging.debug(f"Filtered {filtered} events")

def main():
    logging.basicConfig(level=logging.DEBUG)

    cal = None

    with open(TARGET_ICAL_FILE, 'r') as f:
        cal = icalendar.Calendar.from_ical(f.read())
        filter_events_by_keyword(cal)

        with open(PRIMARY_ICAL_FILE, 'r') as f2:
            filter_duplicates(f2.read(), cal)

    for (i, event) in enumerate(new_cal.walk("VEVENT")):
        if i > DEBUG_EVENT_COUNT:
            break
        logging.debug(event.get('summary'))

if __name__ == "__main__":
    main()