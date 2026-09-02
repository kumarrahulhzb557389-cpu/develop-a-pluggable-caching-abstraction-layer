import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import App from '../App.jsx';

describe('Universal Cache Manager Dashboard Frontend Tests', () => {
  beforeEach(() => {
    // Mock fetch for all endpoints
    global.fetch = vi.fn((url) => {
      if (url.includes('/backend')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ backend: 'memory', status: 'healthy' }),
        });
      }
      if (url.includes('/backends')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ active: 'memory', available: ['memory', 'redis', 'memcached'] }),
        });
      }
      if (url.includes('/health')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ status: 'healthy', backend: 'memory', latency_ms: 0.05 }),
        });
      }
      if (url.includes('/stats')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            hits: 12,
            misses: 4,
            total_reads: 16,
            hit_ratio_percent: 75.0,
            sets: 10,
            deletes: 2,
            clears: 1,
            uptime_seconds: 120,
          }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
      });
    });
  });

  it('renders brand header, active backend, and navigation tabs', async () => {
    const { container } = render(<App />);

    expect(screen.getByText('Universal-Cache-Manager')).toBeInTheDocument();
    expect(screen.getByText(/SIH P-003/i)).toBeInTheDocument();

    // Verify tabs

    expect(container.querySelector('#tab-overview')).toBeInTheDocument();
    expect(container.querySelector('#tab-operations')).toBeInTheDocument();
    expect(container.querySelector('#tab-management')).toBeInTheDocument();
    expect(container.querySelector('#tab-analytics')).toBeInTheDocument();
    expect(container.querySelector('#tab-benchmark')).toBeInTheDocument();
    expect(container.querySelector('#tab-health')).toBeInTheDocument();
    expect(container.querySelector('#tab-logs')).toBeInTheDocument();
  });

  it('switches between tabs accurately', async () => {
    const { container } = render(<App />);

    // 1. Switch to Cache Operations
    fireEvent.click(container.querySelector('#tab-operations'));
    expect(screen.getByText('SINGLE KEY CACHE OPERATIONS')).toBeInTheDocument();
    expect(screen.getByText('BATCH OPERATIONS (MGET / MSET / MDELETE)')).toBeInTheDocument();

    // 2. Switch to Backend Management
    fireEvent.click(container.querySelector('#tab-management'));
    expect(screen.getByText('RUNTIME BACKEND SWITCHER')).toBeInTheDocument();
    expect(screen.getByText('Switch to Redis')).toBeInTheDocument();
    expect(screen.getByText('Switch to Memcached')).toBeInTheDocument();

    // 3. Switch to Visual Analytics
    fireEvent.click(container.querySelector('#tab-analytics'));
    expect(screen.getByText('HIT VS MISS DISTRIBUTION')).toBeInTheDocument();
    expect(screen.getByText('OPERATIONS BREAKDOWN')).toBeInTheDocument();

    // 4. Switch to Benchmark
    fireEvent.click(container.querySelector('#tab-benchmark'));
    expect(screen.getByText('LIVE MULTI-BACKEND PERFORMANCE BENCHMARK')).toBeInTheDocument();
    expect(screen.getByText(/Execute Real Benchmark/i)).toBeInTheDocument();

    // 5. Switch to Health & Diagnostics
    fireEvent.click(container.querySelector('#tab-health'));
    expect(screen.getByText('ACTIVE BACKEND DIAGNOSTICS')).toBeInTheDocument();

    // 6. Switch to Operation Logs
    fireEvent.click(container.querySelector('#tab-logs'));
    expect(screen.getByText('RECENT OPERATION AUDIT TRAIL')).toBeInTheDocument();
  });


  it('allows configuring and saving administrative API key', async () => {
    render(<App />);

    const apiKeyBtn = screen.getByText(/Set API Key/i);
    fireEvent.click(apiKeyBtn);

    expect(screen.getByText('Administrative API Key')).toBeInTheDocument();
    const input = screen.getByLabelText('API Key');
    fireEvent.change(input, { target: { value: 'secret-test-key-123' } });

    const saveBtn = screen.getByText('Save Key');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.queryByText('Administrative API Key')).not.toBeInTheDocument();
    });
  });
});
