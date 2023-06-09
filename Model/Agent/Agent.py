import random
import time
from .State import GroupState, ExploreState, PredatorState, RebelState, State, YearningState

class Agent:
    def __init__(self, id, hex, memory, attractionCoefficient, pheromone_strength=10, health=100, movement_speed=1):
        self.id = id
        self.health = health
        self.movement_speed = movement_speed
        self.attractionCoefficient = attractionCoefficient
        
        self.hex=hex

        self.state = GroupState()
        self.sensing_radius = 20
        self.communication_radius = 40
        self.comfort_radius = 5
        self.memory = memory
        self.pheromone_strength = pheromone_strength

        self.cached_state=None

        self.situate_at_hex(hex, False)

    
    #Moves the agent from one cell to a neighbor. 

    def move(self,nextHex):
        self.remove_from_hex(self.hex)
        self.situate_at_hex(nextHex)        

    def situate_at_hex(self, hex, inspectFlag=True):
        if inspectFlag:
            self.inspect()

        hex.setColour(self.state.color)
        hex.addAgent(self)
        self.hex=hex
    
    def remove_from_hex(self,hex):
        timer = 1000/(self.movement_speed*self.state.getSpeedMultiplier())
        self.hex.trail.add((self.id, self.pheromone_strength, timer, timer))
        hex.removeAgent(self)
        
        if not hex.agents and not hex.site:
            hex.setDefaultColour()
        elif hex.site:
            hex.setColour(hex.site.siteColour)


    #Agent's Sensor reading is used to update decision vectors
    def getIntent(self, reading):
        decisionVectors = self.getDecisionVectors(reading)
        if decisionVectors:
            sum_q,sum_r,sum_intent = 0,0,0
            for (q,r,intent) in decisionVectors:
                sum_q+=q*intent
                sum_r+=r*intent
                sum_intent+=intent
            
            if sum_intent:
                q, r = round(sum_q/sum_intent), round(sum_r/sum_intent)
                if q==0 and r==0:
                    q,r = self.getRandomDirection()
            else:
                q,r = self.getRandomDirection()
        else:
            q,r = self.getRandomDirection()

        q+=self.hex.q
        r+=self.hex.r

        if self.possible_moves.get((q,r))!=None:
            return self.possible_moves.get((q,r))
        else:
            return random.choice(list(self.possible_moves.values()))
    
    def getDecisionVectors(self, reading):
        decisionVectors = []
        
        # Agent will look for trails only if it's in exploreState for more than 10s or if it's in predatorState
        if (isinstance(self.state, ExploreState) and self.state.timer>self.state.inflection) or isinstance(self.state,PredatorState):
            if reading.trails:
                for trailHex in reading.trails.values():
                    if self.hex.computeDistance(trailHex):
                        q,r = self.get_step_to_target(trailHex)
                        # getting hex's relative position to self.hex
                        q,r = q-self.hex.q, r-self.hex.r

                        total_pheromone_strength=0
                        for item in trailHex.trail:
                            id, pheromone_strength, timer, sacredTimer = item
                            if id!=self.id:
                                total_pheromone_strength += pheromone_strength
                        
                        total_pheromone_strength/=1000
                        intent = total_pheromone_strength/(self.hex.computeDistance(trailHex))**2
                        intent*=self.state.getIntentToTrailMultiplier()
                        
                        decisionVectors.append((q,r,intent))

        # Agent will look for sites only if it's in exploreState or groupState
        if isinstance(self.state, ExploreState) or isinstance(self.state, GroupState): 
            if reading.sites:
                for loc in reading.sites.keys():
                    if not self.memory.contains(loc):
                        site = reading.sites[loc]

                        if self.hex.computeDistance(site.hex):
                            q,r = self.get_step_to_target(site.hex)
                            q,r = q-self.hex.q, r-self.hex.r

                            intent = site.quality/(self.hex.computeDistance(site.hex))**2
                            intent*=self.state.getIntentToSiteMultiplier()

                            decisionVectors.append((q,r,intent))
        
        # Agent will look for other agents if it's in exploreState for more than 10s or if it's in groupState or predatorState or YearningState
        if (isinstance(self.state, ExploreState) and self.state.timer>self.state.inflection) or isinstance(self.state, GroupState) or isinstance(self.state, PredatorState) or isinstance(self.state, YearningState):
            if reading.agents:
                for agents in reading.agents.values():
                    for agent in agents:
                        if self.hex.computeDistance(agent.hex):
                            q,r = self.get_step_to_target(agent.hex)
                            q,r = q-self.hex.q, r-self.hex.r

                            if isinstance(self.state, YearningState):
                                intent = 1
                            else:
                                intent = self.getAttractionCoefficient(agent)/(self.hex.computeDistance(agent.hex))**2
                                intent*=self.state.getIntentToAgentMultiplier()

                            decisionVectors.append((q,r,intent))

        if isinstance(self.state, RebelState) and self.state.direction:
            q,r = self.state.direction
            decisionVectors.append((q,r,1))
        
        return decisionVectors 
    
    def getRandomDirection(self):
        directions = [(1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1)]
        return random.choice(directions)


    #Gets neighboring cells the agent can move to
    def updateAvailableMoves(self, availableMoves):
        self.possible_moves = availableMoves


    #Inspects the hex it is currently at and adds its information to memory
    def inspect(self):
        if self.hex.site:
            if not self.memory.contains((self.hex.q,self.hex.r)):
                self.add_to_memory(self.hex.site.quality)
                self.observer.notify(self)
                
                location, value, timestamp = self.memory.get_most_recent()
                for agents in self.nearby_agents.values():
                    for agent in agents:
                        agent.add_to_memory(value, location, timestamp)
                        
    def add_to_memory(self, value, location=None, timestamp=None):
        if location is None:
            location = (self.hex.q, self.hex.r)

        if timestamp is None:
            timestamp = time.time()
        
        self.memory.set(location, value, timestamp)
    
    def get_from_memory(self, location):
        return self.memory.get(location)
    

    #Gets next hex to move to in order to reach target
    def get_step_to_target(self, target):
        distance_to_target = self.hex.computeDistance(target)

        q = self.linearInterpolate(self.hex.q, target.q, 1/distance_to_target)
        r = self.linearInterpolate(self.hex.r, target.r, 1/distance_to_target)
        s = self.linearInterpolate(self.hex.s, target.s, 1/distance_to_target)

        q,r,s = self.round_to_hexCoordinates(q, r, s)

        return q,r


    def linearInterpolate(self, a, b, multiplier):
        return a + (b-a) * multiplier

    def round_to_hexCoordinates(self,q,r,s):
        round_q = round(q)
        round_r = round(r)
        round_s = round(s)

        q_diff = abs(round_q - q)
        r_diff = abs(round_r - r)
        s_diff = abs(round_s - s)

        if q_diff > r_diff and q_diff > s_diff:
            round_q = -round_r-round_s
        elif r_diff > s_diff:
            round_r = -round_q-round_s
        else:
            round_s = -round_q-round_r

        return round_q, round_r, round_s
    
    #Calculates the attraction between agents
    def getAttractionCoefficient(self,other):
        return self.attractionCoefficient
    
    def getMovementSpeed(self):
        return self.movement_speed*self.state.getSpeedMultiplier()


    # AgentEngine is attached as an observer
    def attach_observer(self, observer):
        self.observer = observer

    def set_nearby_agents(self,nearby_agents):
        self.nearby_agents = nearby_agents
    
    def setState(self,state):
        self.state = state
