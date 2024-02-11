import icalendar
import icalevents.icalevents as icalevents
import logging

PRIMARY_ICAL_FILE = "./personal.ics"
TARGET_ICAL_FILE = "./work.ics"
FILTER_PHRASES = ["OOF", "Blocked"]

DEBUG_EVENT_COUNT = 10

def filter_duplicates(primary_calender_content : str, target_calendar : icalendar.Calendar) -> icalendar.Calendar:
    """
    Filters events from the target calendar that are already in the primary calendar.
    Due to the way the icalevents module works, the primary calendar is passed as a string and re-parsed every time :/
    See https://github.com/jazzband/icalevents/issues/130

    primary_calender_content: The iCalendar content of the primary calendar as a string
    target_calendar: The target calendar to filter
    """

    for event in target_calendar.walk("VEVENT"):
        result = icalevents.events(
            string_content = primary_calender_content,
            start = event.get('DTSTART').dt,
            end = event.get('DTEND').dt,
            sort = True)
        

def filter_events_by_keyword(cal : icalendar.Calendar) -> icalendar.Calendar:
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

    return cal

def main():
    logging.basicConfig(level=logging.DEBUG)

    new_cal = None

    with open(TARGET_ICAL_FILE, 'rb') as f:
        cal = icalendar.Calendar.from_ical(f.read())
        new_cal = filter_events_by_keyword(cal)

    for (i, event) in enumerate(new_cal.walk("VEVENT")):
        if i > DEBUG_EVENT_COUNT:
            break
        logging.debug(event.get('summary'))

if __name__ == "__main__":
    main()