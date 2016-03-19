Evgeny Naumov's fabulous nutrition tracker. All rights reserved.

dependencies: to run anything you first need to install these python libraries:
    numpy
    click
    fastcache
    pyyaml

they're all probably in pypi, just use pip.


Make 'food.py' executable and symlink to it from a bin directory for your
convenience.

Basic use cycle:

`food find whatever` to find food 'whatever' and get its USDA db codes
`food info code` to get nutrition info about a particular food. At this point
you may with to add it to the recipe 'usda foods' table. More on that later.
`food eat somefood`: eat a food, recording it in the log.
`food review`: view the log, enriched with nutrition information. It takes some
arguments you can figure out from the code.

Basic explanation of the configs:

recipes.yaml:
    contains four tables: 
        - 'usda foods' mapping your name for a food to USDA codes;
        - 'usda corrections', mapping your name for a food to entries you wish
          modified in the nutrition information received from the USDA API. Use
          this to add Iodine and Molybdenum, etc.
        - 'recipes' giving a shorthand name for a collection of foods eaten
          together. Their nutrient values will be automatically found and
          aggregated. Must consist of foods or other recipes.
          IMPORTANT: amounts for foods are given in grams, while amounts for
          sub-recipes are given in multiples. If you mess this up you will
          probably notice in the review.
        - 'custom foods' defines a non-USDA food by giving the nutrient values
          (per 100 g). No error checking is done on this so check for typos.
    
    this file comes with some pre-initialized foods from the maestro's own
    repertoire, so it should be obvious what to do.

goal.yaml:
    enter a goal for yourself. There are lots of confusing fields, ignore them,
    you probably only care about min and max. I'll get back to those later.

plan.yaml
    currently does nothing

cache.json
    keeps your personal data for upload to the NSA when you are not looking.
    do not touch on pain of waterboarding.

config.yaml
    contains the config, which is, namely:
    - the 'reports' table, defining the types of report you want `food review
      reportname` to generate in the viewer. comes with some nice defaults.
    - 'report' - named similarly to 'reports' but does nothing. do not touch
      since I might implement it later.
