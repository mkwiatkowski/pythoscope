from reverend.thomas import Bayes

guesser = Bayes()
guesser.train('fish', 'salmon trout cod carp')
guesser.train('fowl', 'hen chicken duck goose')

guesser.guess('chicken tikka marsala')

guesser.untrain('fish','salmon carp')
