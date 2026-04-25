'use client';

import { createContext, useContext, useState, type ReactNode } from 'react';

export type City = 'all' | 'nyc' | 'london';

const CITY_MAP: Record<City, { center: [number, number]; zoom: number }> = {
  nyc:    { center: [40.73,  -73.97], zoom: 12 },
  london: { center: [51.505, -0.09],  zoom: 12 },
  all:    { center: [40.73,  -73.97], zoom: 12 },
};

type CityContextValue = {
  city: City;
  setCity: (c: City) => void;
  mapCenter: [number, number];
  mapZoom: number;
};

const CityContext = createContext<CityContextValue>({
  city: 'nyc',
  setCity: () => {},
  mapCenter: CITY_MAP.nyc.center,
  mapZoom: CITY_MAP.nyc.zoom,
});

export function CityProvider({ children }: { children: ReactNode }) {
  const [city, setCity] = useState<City>('nyc');
  return (
    <CityContext.Provider
      value={{
        city,
        setCity,
        mapCenter: CITY_MAP[city].center,
        mapZoom: CITY_MAP[city].zoom,
      }}
    >
      {children}
    </CityContext.Provider>
  );
}

export function useCity(): CityContextValue {
  return useContext(CityContext);
}
