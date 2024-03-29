import icalendar
import logging
import json
import typing
import urllib3

from dateutil import rrule
from http.server import BaseHTTPRequestHandler
from os import path
from thefuzz import fuzz
from time import perf_counter
from urllib.parse import parse_qs

CONFIG_FILE = path.join("config", "config.json")

FUZZY_MATCH_THRESHOLD = 90
DEBUG_EVENT_COUNT = 10

def get_config() -> typing.Dict:
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def events_overlap(event1 : icalendar.Event, event2 : icalendar.Event, time_only : bool = False) -> bool:
    """
    Determines if two events overlap in time. If time_only is True, only the time of day is considered;
    this is used for recurring events where we compare the dates based on additional complex criteria.
    """

    try:
        start1 = event1.get('DTSTART').dt
        end1 = event1.get('DTEND').dt
        start2 = event2.get('DTSTART').dt
        end2 = event2.get('DTEND').dt
    except AttributeError:
        # TODO: Handle this more elegantly. This function gets called multiple times so it's spamming
        # the log
        #
        # Turns out iCalendar VEVENTS do not require DTEND or DURATION. From
        # https://icalendar.org/iCalendar-RFC-5545/3-6-1-event-component.html:
        #
        # "For cases where a "VEVENT" calendar component specifies a "DTSTART" property with a DATE
        # value type but no "DTEND" nor "DURATION" property, the event's duration is taken to be
        # one day."
        #
        # If you export a Google Calendar to an .ics file, it seems to excludes DTEND for very old
        # events, even if they were NOT all-day events. This is unlikely to be a problem in
        # practice since we'll use the on-demand iCalendar feed, which probably doesn't go that
        # far back. For now we just ignore any such events.
        logging.warning("One or more events is missing a start or end time")
        return False

    # Check for type mismatch, i.e. if one event has a datetime but the other only has a date
    if type(start1) != type(start2) or type(end1) != type(end2):
        return False

    if time_only:
        start1 = start1.time()
        end1 = end1.time()
        start2 = start2.time()
        end2 = end2.time()

    return start1 <= end2 and end1 >= start2

def recurring_events_are_equal(event1 : icalendar.Event, event2 : icalendar.Event) -> bool:
    """
    Compares two recurring events to see if they're equal. Only works for recurring events.
    Equality is determined by comparing the SUMMARY (title) and RRULE properties of the event.
    
    IMPORTANT: This almost certainly won't work for recurrences that happen on an hourly,
    minutely, or secondly basis.
    """

    assert(event1.get('RRULE') is not None)
    assert(event2.get('RRULE') is not None)

    # First ensure that the names of the events are similar enough
    # TODO: Use ratio instead of partial_ratio. Need download updated ICS for work calendar.
    if not fuzz.partial_ratio(event1.get('SUMMARY'), event2.get('SUMMARY')) >= FUZZY_MATCH_THRESHOLD:
        return False
    
    rule1 = rrule.rrulestr(
        event1.get('RRULE').to_ical().decode(icalendar.parser_tools.DEFAULT_ENCODING),
        dtstart = event1.get('DTSTART').dt)
    
    rule2 = rrule.rrulestr(
        event2.get('RRULE').to_ical().decode(icalendar.parser_tools.DEFAULT_ENCODING),
        dtstart = event2.get('DTSTART').dt)

    # It turns out that comparing iCalendar recurrence rules in an intelligent way is quite
    # difficult. The rrule object doesn't even implement __eq__, as two rrules created from the
    # exact same string will not be considered equal.
    #
    # Additionally, there are some details of the rrule that we want to ignore. We don't care if the
    # recurrences start and end on the exact same dates, for example, because the recurrence count
    # might be different between different calendars. We do want the events to overlap, but we don't
    # care if the overlap is exact, as one event might be padded out on one calendar.
    #
    # As a workaround, we create a new rule by replacing the irrelevant parts of the second rule
    # with the values from the first, and then comparing the output strings. This is a huge hack,
    # but it's the best I can come up with given the time constraints I'm working under.
    dummy_rule = rule2.replace(dtstart = rule1._dtstart, wkst = rule1._wkst,
                               count = rule1._count, until = rule1._until)

    if not str(rule1) == str(dummy_rule):
        return False
    
    # From here we can (probably) assume that the events have the same recurrence rules, but because
    # we ignored the start and end dates, we need to check that the events actually overlap.
    # If both rules recur indefinitely, they overlap by definition. If one or both have a count,
    # we can check that the other rule has at least one event between the start and end date of the
    # other.

    if rule1._count is not None or rule1._until is not None:
        dtstart = rule1._dtstart
        dtend = rule1[-1]

        if len(rule2.between(dtstart, dtend)) == 0:
            return False
    
    elif rule2._count is not None or rule2._until is not None:
        dtstart = rule2._dtstart
        dtend = rule2[-1]

        if len(rule1.between(dtstart, dtend)) == 0:
            return False
        
    # Now, finally, let's check if the event times overlap. We've already validated that the recurrence
    # rules are the same and that they overlap, so we should only have to care about the time of day.
    return events_overlap(event1, event2, time_only = True)

def filter_duplicates(primary_calendar : icalendar.Calendar, target_calendar : icalendar.Calendar) -> None:
    """
    Filters events from the target calendar that are already in the primary calendar.

    primary_calendar_content: The source calendar to filter against
    target_calendar: The target calendar to filter
    """

    logging.debug("Filtering duplicate events")

    filtered = 0

    # First filter recurring events. Note: this assumes that duplicate recurring events will be
    # marked as recurring on both calendars; i.e. it doesn't handle the case where one calendar
    # has a recurring event and the other has a single event with the same title.
    for event1 in primary_calendar.walk("VEVENT"):

        if event1.get('RRULE') is None:
            continue

        for event2 in target_calendar.walk("VEVENT"):

            if event2.get('RRULE') is None:
                continue

            if recurring_events_are_equal(event1, event2):
                logging.debug(f"Filtering duplicate recurring event: {event2.get('summary')}")
                target_calendar.subcomponents.remove(event2)
                filtered += 1

    # Now we can filter individual duplicate events
    for event1 in primary_calendar.walk("VEVENT"):

        if event1.get('RRULE') is not None:
            continue

        for event2 in target_calendar.walk("VEVENT"):

            if event2.get('RRULE') is not None:
                continue

            if events_overlap(event1, event2) and \
                fuzz.partial_ratio(event1.get('SUMMARY'), event2.get('SUMMARY')) >= FUZZY_MATCH_THRESHOLD:
                logging.debug(f"Filtering duplicate event: {event2.get('SUMMARY')}")
                target_calendar.subcomponents.remove(event2)
                filtered += 1

    logging.info(f"Filtered {filtered} duplicate events")

def filter_events_by_keyword(keywords : typing.List[str], calendar : icalendar.Calendar) -> None:
    """
    Filters events from the calendar that contain any of the FILTER_PHRASES.

    calendar: The calendar to filter
    """

    logging.debug("Filtering events by keyword")

    filtered = 0

    # Loop through events in the calendar and remove the ones where the title (SUMMARY) contains
    # any of the FILTER_PHRASES. Note that it's typically not safe to remove items from a list
    # while iterating over it, but the icalendar.Component.walk is not an iterator per se: it
    # recursively copies the subcomponents into a list and then returns that list, so we're
    # not modifying the same list we're iterating over.
    for event in calendar.walk("VEVENT"):
        for phrase in keywords:
            if phrase in event.get('SUMMARY'):
                logging.debug(f"Filtering event: {event.get('summary')}")
                calendar.subcomponents.remove(event)
                filtered += 1

    if filtered > 0:
        logging.info(f"Filtered {filtered} events by keyword")

def get_filtered_calendar(config : typing.Dict) -> icalendar.Calendar:

    http = urllib3.PoolManager()

    primary_calendar_content = None
    target_calendar_content = None
    try:
        primary_calendar_content = http.request("GET", config["primary_ical"]).data
    except Exception as e:
        logging.error(f"Error fetching primary calendar: {e}")
        return None

    try:
        target_calendar_content = http.request("GET", config["target_ical"]).data
    except Exception as e:
        logging.error(f"Error fetching target calendar: {e}")
        return None

    primary_calendar = icalendar.Calendar.from_ical(primary_calendar_content)
    target_calendar = icalendar.Calendar.from_ical(target_calendar_content)

    filter_events_by_keyword(config["filter_keywords"], target_calendar)
    filter_duplicates(primary_calendar, target_calendar)

    return target_calendar

class handler(BaseHTTPRequestHandler):
    def do_GET(self):

        t0 = perf_counter()

        config = get_config()
    
        logging.basicConfig(level = logging.DEBUG if config["debug"] == "true" else logging.INFO)
        qs = parse_qs(urllib3.util.parse_url(self.path).query)

        logging.debug(qs)

        client_secret = qs.get("secret")
        if type(client_secret) == list:
            client_secret = client_secret[0]

        if not client_secret or client_secret != config["secret"]:
            logging.debug("Client secret is invalid.")
            self.send_response(403)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/calendar")
        self.end_headers()

        filtered_calendar = get_filtered_calendar(config)
        self.wfile.write(filtered_calendar.to_ical())

        logging.debug(f"Execution time: {perf_counter() - t0:.3f}s")

# if __name__ == "__main__":
#     main()