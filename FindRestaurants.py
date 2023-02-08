from datetime import datetime
from dateutil.parser import *
import json
import os
import re
import sys

g_ERR_OK = 0  # error-level of 0 means no error

g_restaurants_filename = 'rest_hours.json'
g_script_folder_path = os.path.dirname(os.path.abspath(__file__))
g_restaurants_file_path = os.path.join(g_script_folder_path, g_restaurants_filename)

g_days_of_week = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')


# ============================== File functions


def read_restaurant_schedules(restaurant_file_path):
    with open(restaurant_file_path) as restaurant_file:
        restaurant_data = json.load(restaurant_file)
    restaurants = [Restaurant(r['name'], r['times']) for r in restaurant_data]

    # show any parsing errors (skipped schedules for the given restaurant)
    for r in restaurants:
        if r.log_messages:
            log_strings = '\n\t'.join(r.log_messages)
            print(f'{r.name}:\n\t{log_strings}')

    return restaurants


# ============================== User interaction functions


def prompt_for_date_and_time():
    print('\n========== Find Open Restaurants')

    while True:
        target_datetime_string = input('Enter the desired date and time (none to exit): ')
        if not target_datetime_string:
            return None

        try:
            # Note: The parser defaults most segments that are omitted (year, month, day, minutes)
            target_datetime = parse(target_datetime_string)
            print(f'\tUsing time: {datetime.strftime(target_datetime, "%Y-%m-%d %I:%M %p (%a)")}')
            return target_datetime
        except ParserError:
            print(f'\tCould not parse date/time string "{target_datetime_string}". Please re-enter.')
            continue


def show_open_restaurant_names(open_restaurants, dow, time):
    names = [r.name for r in open_restaurants]
    names.sort()
    names_string = '\n\t'.join(names)  # todo: enhancement: also show how many minutes till close (if <= 60 min)
    print(f'{len(names)} restaurants are open on "{dow}" at "{time}" (24-hr time):\n\t{names_string}')


# ============================== Backend functions


def transform_datetime_to_dow_and_time(datetime_object):
    dow = datetime.strftime(datetime_object, '%a')
    hr = datetime.strftime(datetime_object, '%H')
    minute = datetime.strftime(datetime_object, '%M')
    return dow, f'{hr}{minute}'


def enumerate_days_of_week(start_dow, opt_end_dow):
    if start_dow is None:
        return []
    if opt_end_dow is None:
        opt_end_dow = start_dow

    start_index = g_days_of_week.index(start_dow)
    end_index = g_days_of_week.index(opt_end_dow)
    if end_index < start_index:  # need to wrap around end of the week back to the beginning
        end_index += len(g_days_of_week)

    days_of_two_weeks = g_days_of_week + g_days_of_week
    dows = [days_of_two_weeks[i] for i in range(start_index, end_index + 1)]
    return dows


def get_time_range(start_time, end_time):
    if start_time is None or end_time is None or start_time == end_time:
        return []
    start = f'{start_time.hour:02}{start_time.minute:02}'
    end = f'{end_time.hour:02}{end_time.minute:02}'
    if end == '0000':
        end = '2400'  # convert midnight at BEGINNING of the day to midnight at the END of the day
    return start, end


def get_time_ranges(start_hr, start_min, start_ampm, end_hr, end_min, end_ampm):
    # parse the start and end times
    time_format = '%I:%M %p'
    start_time = datetime.strptime(f'{start_hr}:{start_min} {start_ampm}', time_format)
    end_time = datetime.strptime(f'{end_hr}:{end_min} {end_ampm}', time_format)
    next_day_start_time = None
    next_day_end_time = None

    # check for times that wrap around the date boundary (midnight)
    if end_time < start_time:  # time range wrapped to the next day
        day_boundary = datetime.strptime('12:00 am', time_format)
        next_day_start_time = day_boundary
        next_day_end_time = end_time
        end_time = day_boundary

    times = get_time_range(start_time, end_time)
    next_day_times = get_time_range(next_day_start_time, next_day_end_time)
    return times, next_day_times


def get_next_dow(dow):
    next_dow_index = g_days_of_week.index(dow) + 1
    if next_dow_index == len(g_days_of_week):
        next_dow_index = 0  # wrap around end of the week back to the first day
    return g_days_of_week[next_dow_index]


def augment_map(mapping, key, values):
    if key not in mapping.keys():
        mapping[key] = []
    mapping[key].append(values)


def parse_schedule(schedule_string, log_messages):
    if not schedule_string:
        return {}

    # define regular expressions that represent schedules (for parsing)
    hyphen = r'\s*-\s*'

    hr = r'(1|2|3|4|5|6|7|8|9|10|11|12|01|02|03|04|05|06|07|08|09)'
    minute = r'(:(00|30))?'
    ampm = r'\s*(am|pm)'
    time = fr'{hr}{minute}{ampm}'
    time_range = fr'{time}{hyphen}{time}'

    dow = r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun)'
    dow_range = fr'{dow}({hyphen}{dow})?'
    dow_ranges = fr'{dow_range}(,\s*{dow_range})?'  # support ONE OR TWO day ranges (separated by commas)

    schedule = fr'{dow_ranges}\s+{time_range}'

    # matching groups (one-origin):
    #   start_dow
    #   optional hyphen and end_dow
    #   end_dow (optional)
    #   optional comma and additional dow range
    #   start_dow2 (optional)
    #   optional hyphen and end_dow2
    #   end_dow2 (optional)
    #   start_hr
    #   optional colon and minute
    #   start_min (optional)
    #   start_ampm
    #   end_hr
    #   optional colon and minute
    #   end_min (optional)
    #   end_ampm

    # Note: if the start_ampm is "am" and the end_ampm is "pm", that's fine (still in the same day), but if the start
    # is "pm" and the end is "am", then create TWO ranges of time (one for each separate day)

    match = re.match(schedule, schedule_string)
    if match is None:
        log_messages.append(f'Warning: Unexpected format for schedule "{schedule_string}". '
                            'Please fix the data or the regular expressions for parsing the data.')
        return {}

    start_dow, opt_hyphen, opt_end_dow, \
        opt_comma, \
        opt_start_dow2, opt_hyphen2, opt_end_dow2, \
        start_hr, opt_start_colon, start_min, start_ampm, \
        end_hr, opt_end_colon, end_min, end_ampm \
        = match.groups()
    if not start_min:
        start_min = '00'
    if not end_min:
        end_min = '00'
    times, next_day_times = get_time_ranges(start_hr, start_min, start_ampm, end_hr, end_min, end_ampm)

    dow_to_times = {}   # mapping each day-of-week (key) to a list of open time ranges (open time, close time)
    dows = enumerate_days_of_week(start_dow, opt_end_dow)
    dows2 = enumerate_days_of_week(opt_start_dow2, opt_end_dow2)
    for dow in dows + dows2:
        augment_map(dow_to_times, dow, times)
        if next_day_times:
            next_dow = get_next_dow(dow)
            augment_map(dow_to_times, next_dow, next_day_times)

    return dow_to_times


def map_days_to_times(schedule_strings, log_messages):
    mapping = {}
    for schedule_string in schedule_strings:
        dow_to_open_ranges = parse_schedule(schedule_string, log_messages)
        for dow in dow_to_open_ranges:
            for open_range in dow_to_open_ranges[dow]:
                augment_map(mapping, dow, open_range)

    return mapping


class Restaurant:
    def __init__(self, name, schedule_strings):
        self.name = name
        self.schedule_strings = schedule_strings
        self.log_messages = []
        self.open_days_to_times = map_days_to_times(schedule_strings, self.log_messages)

    def __str__(self):
        desc = f'Restaurant "{self.name}" with schedule "{self.schedule_strings}"\n'
        if self.log_messages:
            desc += f'Logs: "{self.log_messages}"\n'
        desc += 'Parsed schedule:\n'
        for dow in self.open_days_to_times:
            desc += f'\t{dow}: {self.open_days_to_times[dow]}\n'
        return desc

    def is_open(self, dow, time):
        if dow not in self.open_days_to_times.keys():
            return False
        for open_time, close_time in self.open_days_to_times[dow]:
            if open_time <= time < close_time:
                return True
        return False


def get_open_restaurants(restaurants, dow, time):
    open_restaurants = [r for r in restaurants if r.is_open(dow, time)]
    return open_restaurants


# ============================== Program functions


def main():
    print(f'========== Reading restaurant file "{g_restaurants_file_path}"...')
    all_restaurants = read_restaurant_schedules(g_restaurants_file_path)
    print(f'\t{len(all_restaurants)} restaurants loaded.')

    while True:
        datetime_object = prompt_for_date_and_time()
        if datetime_object is None:
            return g_ERR_OK

        dow, time = transform_datetime_to_dow_and_time(datetime_object)
        open_restaurants = get_open_restaurants(all_restaurants, dow, time)
        show_open_restaurant_names(open_restaurants, dow, time)


def run_tests():
    print('Running unit tests...')
    try:
        # ==================== transform datetime into dow and time range
        datetime_format = '%Y-%m-%d %I:%M %p'
        date_time = datetime.strptime('2023-02-03 1:01 am', datetime_format)
        assert transform_datetime_to_dow_and_time(date_time) == ('Fri', '0101')

        date_time = datetime.strptime('2023-02-04 1:20 pm', datetime_format)
        assert transform_datetime_to_dow_and_time(date_time) == ('Sat', '1320')

        date_time = datetime.strptime('2023-02-05 2:35 pm', datetime_format)
        assert transform_datetime_to_dow_and_time(date_time) == ('Sun', '1435')

        # ==================== augment_map
        test_map = {}
        tuple_value1 = ('1', '2')
        augment_map(test_map, 'a', tuple_value1)
        assert len(test_map.keys()) == 1 and 'a' in test_map.keys() and test_map['a'] == [tuple_value1]

        tuple_value2 = ('3',)
        augment_map(test_map, 'a', tuple_value2)
        assert len(test_map.keys()) == 1 and 'a' in test_map.keys() and test_map['a'] == [tuple_value1, tuple_value2]

        tuple_value3 = ('1',)
        augment_map(test_map, 'b', tuple_value3)
        assert len(test_map.keys()) == 2 and 'b' in test_map.keys() and \
               test_map['a'] == [tuple_value1, tuple_value2] and \
               test_map['b'] == [tuple_value3]

        # ==================== enumerate_days_of_week
        assert enumerate_days_of_week(None, None) == []
        assert enumerate_days_of_week('Mon', None) == ['Mon']
        assert enumerate_days_of_week('Mon', 'Mon') == ['Mon']
        assert enumerate_days_of_week('Mon', 'Tue') == ['Mon', 'Tue']
        assert enumerate_days_of_week('Mon', 'Wed') == ['Mon', 'Tue', 'Wed']
        assert enumerate_days_of_week('Mon', 'Sun') == ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        assert enumerate_days_of_week('Sat', 'Mon') == ['Sat', 'Sun', 'Mon']  # can wrap around end of week

        # ==================== get_time_range
        time_format = '%I:%M %p'
        start_time = datetime.strptime('11:00 am', time_format)
        end_time = start_time
        assert len(get_time_range(None, None)) == 0
        assert len(get_time_range(None, end_time)) == 0
        assert len(get_time_range(start_time, None)) == 0
        assert len(get_time_range(start_time, end_time)) == 0   # start and end times are the same

        end_time = datetime.strptime('11:30 am', time_format)
        time_range = get_time_range(start_time, end_time)
        assert time_range == ('1100', '1130')

        end_time = datetime.strptime('12:00 pm', time_format)
        time_range = get_time_range(start_time, end_time)
        assert time_range == ('1100', '1200')

        end_time = datetime.strptime('11:30 pm', time_format)
        time_range = get_time_range(start_time, end_time)
        assert time_range == ('1100', '2330')

        start_time = datetime.strptime('11:00 pm', time_format)
        end_time = datetime.strptime('12:00 am', time_format)   # end time of midnight
        time_range = get_time_range(start_time, end_time)
        assert time_range == ('2300', '2400')   # midnight end time translates to 2400

        # ==================== enumerate_times_of_day
        times, tomorrow_times = get_time_ranges('11', '00', 'am', '11', '00', 'am')
        assert not times and not tomorrow_times

        times, tomorrow_times = get_time_ranges('11', '00', 'am', '11', '30', 'am')
        assert times == ('1100', '1130') and not tomorrow_times

        times, tomorrow_times = get_time_ranges('11', '00', 'am', '12', '00', 'pm')
        assert times == ('1100', '1200') and not tomorrow_times

        times, tomorrow_times = get_time_ranges('11', '00', 'am', '06', '00', 'pm')
        assert times == ('1100', '1800') and not tomorrow_times

        times, tomorrow_times = get_time_ranges('11', '00', 'pm', '02', '00', 'am')     # extending past midnight
        assert times == ('2300', '2400') and tomorrow_times == ('0000', '0200')     # time ranges in TWO days

        # ==================== get_next_dow
        assert get_next_dow('Mon') == 'Tue'
        assert get_next_dow('Tue') == 'Wed'
        assert get_next_dow('Wed') == 'Thu'
        assert get_next_dow('Thu') == 'Fri'
        assert get_next_dow('Fri') == 'Sat'
        assert get_next_dow('Sat') == 'Sun'
        assert get_next_dow('Sun') == 'Mon'     # wrapping from the end of one week to the beginning of the next

        # ==================== parse_schedule
        log_messages = []
        dow_to_times = parse_schedule('', log_messages)  # missing date(s) and times
        assert not dow_to_times and not log_messages

        log_messages = []
        dow_to_times = parse_schedule('Mon', log_messages)  # has day, but missing times
        assert not dow_to_times and len(log_messages) == 1 and log_messages[0].startswith('Warning')

        log_messages = []
        dow_to_times = parse_schedule('Mon-Fri', log_messages)  # has day range, but missing times
        assert not dow_to_times and len(log_messages) == 1 and log_messages[0].startswith('Warning')

        log_messages = []
        dow_to_times = parse_schedule('Mon 4:00 pm', log_messages)  # has day and start time, but missing end time
        assert len(dow_to_times) == 0 and len(log_messages) == 1

        log_messages = []
        dow_to_times = parse_schedule('Mon 4:00 pm - 5 pm', log_messages)  # has day and times
        assert list(dow_to_times.keys()) == ['Mon'] and len(log_messages) == 0 and \
               dow_to_times['Mon'] == [('1600', '1700')]

        log_messages = []
        dow_to_times = parse_schedule('Mon, Wed 4 pm - 5:00 pm', log_messages)  # has disjoint days
        assert list(dow_to_times.keys()) == ['Mon', 'Wed'] and len(log_messages) == 0 and \
               dow_to_times['Mon'] == [('1600', '1700')] and \
               dow_to_times['Wed'] == [('1600', '1700')]    # the same time range is applied to *each* day

        log_messages = []
        dow_to_times = parse_schedule('Mon-Fri 4pm-11pm', log_messages)  # has one day range
        assert len(dow_to_times) == 5 and list(dow_to_times.keys()) == ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
        for dow in dow_to_times:
            assert dow_to_times[dow] == [('1600', '2300')]  # the same time range is applied to *each* day

        log_messages = []
        dow_to_times = parse_schedule('Mon-Tue, Thu-Fri 4:00 pm - 5:00 pm', log_messages)  # has two dow ranges
        assert list(dow_to_times.keys()) == ['Mon', 'Tue', 'Thu', 'Fri'] and len(log_messages) == 0
        for dow in dow_to_times:
            assert dow_to_times[dow] == [('1600', '1700')]

        log_messages = []
        dow_to_times = parse_schedule('Sun-Mon 10:00 pm - 12:00 am', log_messages)  # times go to midnight
        assert list(dow_to_times.keys()) == ['Sun', 'Mon']
        for dow in dow_to_times:
            assert dow_to_times[dow] == [('2200', '2400')]  # midnight end time represented by 2400

        log_messages = []
        dow_to_times = parse_schedule('Sun 10:00 pm - 2:00 am', log_messages)  # times span midnight
        assert list(dow_to_times.keys()) == ['Sun', 'Mon']
        assert dow_to_times['Sun'] == [('2200', '2400')]    # midnight end time represented by 2400
        assert dow_to_times['Mon'] == [('0000', '0200')]    # midnight start time represented by 0000

        # ==================== _map_days_to_times
        log_messages = []
        dow_to_times = map_days_to_times(['Mon-Thu 10:00pm-11:30pm', 'Fri-Sat 10:00pm-12:30am'], log_messages)
        for dow in dow_to_times:
            expected_times = \
                [('2200', '2330')] if dow in ('Mon', 'Tue', 'Wed', 'Thu') else \
                [('2200', '2400')] if dow == 'Fri' else \
                [('0000', '0030'), ('2200', '2400')] if dow == 'Sat' else \
                [('0000', '0030')]
            assert dow_to_times[dow] == expected_times and not log_messages

        # ==================== Restaurant.is_open:
        test_times = (
            '0000', '0030', '0100', '0130', '0200', '0230', '0300', '0330', '0400', '0430', '0500', '0530',
            '0600', '0630', '0700', '0730', '0800', '0830', '0900', '0930', '1000', '1030', '1100', '1130',
            '1200', '1230', '1300', '1330', '1400', '1430', '1500', '1530', '1600', '1630', '1700', '1730',
            '1800', '1830', '1900', '1930', '2000', '2030', '2100', '2130', '2200', '2230', '2300', '2330',
            '2400'
        )
        schedules = ['Mon-Thu 10:00pm-11:30pm', 'Fri-Sat 10:00pm-12:30am']
        rest = Restaurant('Restaurant Name', schedules)
        for day in g_days_of_week:
            for time in test_times:
                assert rest.is_open(day, time) == \
                       (day in ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat') and '2200' <= time < '2330') or \
                       (day in ('Fri', 'Sat') and time == '2330') or \
                       (day in ('Sat', 'Sun') and time == '0000') or \
                       False

        # ==================== get_open_restaurants
        rest_a = Restaurant('A', ['Mon-Thu 9:00 pm - 11:30 pm', 'Fri-Sat 6:00pm - 12:30am'])
        rest_b = Restaurant('B', ['Mon 8:00 pm - 10:00 pm'])
        rest_c = Restaurant('C', ['Mon-Tue 4:00 pm - 9:30 pm'])
        restaurants = [rest_a, rest_b, rest_c]
        assert [r.name for r in get_open_restaurants(restaurants, 'Mon', '2100')] == ['A', 'B', 'C']
        assert [r.name for r in get_open_restaurants(restaurants, 'Mon', '2000')] == ['B', 'C']
        assert [r.name for r in get_open_restaurants(restaurants, 'Mon', '1700')] == ['C']
        assert [r.name for r in get_open_restaurants(restaurants, 'Sat', '0000')] == ['A']

    except AssertionError:
        print('========== A test failed. Review the errors and fix the failing test.')
        raise
    print('Unit tests finished.')


def load_and_dump_restaurants():
    print(f'Reading restaurant file "{g_restaurants_file_path}"...')
    all_restaurants = read_restaurant_schedules(g_restaurants_file_path)
    print(f'\t{len(all_restaurants)} restaurants loaded.')

    print('Dumping restaurant results...')
    for restaurant in all_restaurants:
        print(f'{restaurant}')


if __name__ == '__main__':
    # Run unit tests, data dump, or the program (mutually exclusive)
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        run_tests()
        sys.exit(g_ERR_OK)

    if len(sys.argv) > 1 and sys.argv[1] == 'dump':
        load_and_dump_restaurants()
        sys.exit(g_ERR_OK)

    sys.exit(main())
