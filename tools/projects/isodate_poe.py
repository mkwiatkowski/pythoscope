from isodate import *

parse_time("2011-04-16 11:51Z")
parse_tzinfo("2011-04-16 11:51Z")
parse_datetime("2011-04-16T11:51Z")
parse_tzinfo("2011-04-16T11:51Z")

for s in ["2011-04-16", "2011-W15-6", "2011-106"]:
    parse_date(s)
