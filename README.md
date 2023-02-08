# byub-coding-exercise-restaurant-schedules

The BYUB-assigned coding exercise, written as a Python script.

If you have Python 3.x installed on your machine, you can run the script from your local repository folder with this command line:

`python FindRestaurants.py`

If you don't have Python 3.x installed, I can supply a Windows executable with the Python interpreter embedded in it.


## Files

`0-assignment.txt`: text of the original assignment and initial considerations that went into the script's design

`FindRestaurants.py`: coded implementation for the assignment (as a single file)

`FindRestaurants.spec`: configuration options for building an executable from the Python script

`rest_hours.json`: BYUB-supplied data for the assignment (must be in the same folder as the script at run time)

## Script execution using Python 3.x

`python FindRestaurants.py`: reads the data file (`rest_hours.json`), prompts the user for a date and time, and shows restaurants that are open at that time

`python FindRestaurants.py test`: runs unit tests, showing error messages if any tests fail

`python FindRestaurants.py dump`: reads the data file (`rest_hours.json`) and dumps the parsed times that each restaurant is open
